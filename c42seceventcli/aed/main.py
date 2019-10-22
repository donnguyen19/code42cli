import json
import keyring
import getpass
from keyring.errors import PasswordDeleteError
from socket import gaierror
from urllib3 import disable_warnings
from urllib3.exceptions import InsecureRequestWarning
from datetime import datetime, timedelta

from py42 import debug_level
from py42 import settings
from py42.sdk import SDK
from c42secevents.extractors import AEDEventExtractor
from c42secevents.common import FileEventHandlers, convert_datetime_to_timestamp
from c42secevents.logging.formatters import AEDDictToCEFFormatter, AEDDictToJSONFormatter

import c42seceventcli.common.common as common
import c42seceventcli.aed.args as aed_args
from c42seceventcli.aed.cursor_store import AEDCursorStore

_SERVICE_NAME_FOR_KEYCHAIN = u"c42seceventcli"


def main():
    args = aed_args.get_args()
    _verify_destination_args(args)

    if args.reset_password:
        _delete_stored_password(args.c42_username)

    handlers = _create_handlers(args)
    _set_up_cursor_store(
        record_cursor=args.record_cursor, clear_cursor=args.clear_cursor, handlers=handlers
    )
    sdk = _create_sdk_from_args(args, handlers)

    if bool(args.ignore_ssl_errors):
        _ignore_ssl_errors()

    if bool(args.debug_mode):
        settings.debug_level = debug_level.DEBUG

    _extract(args=args, sdk=sdk, handlers=handlers)


def _verify_destination_args(args):
    if args.destination_type == "stdout" and args.destination is not None:
        msg = (
            "Destination '{0}' not applicable for stdout. "
            "Try removing '--dest' arg or change '--dest-type' to 'file' or 'server'."
        )
        msg = msg.format(args.destination)
        print(msg)
        exit(1)

    if args.destination_type == "file" and args.destination is None:
        print("Missing file name. Try: '--dest path/to/file'.")
        exit(1)

    if args.destination_type == "server" and args.destination is None:
        print("Missing server URL. Try: '--dest https://syslog.example.com'.")
        exit(1)


def _delete_stored_password(username):
    try:
        keyring.delete_password(_SERVICE_NAME_FOR_KEYCHAIN, username)
    except PasswordDeleteError:
        return


def _ignore_ssl_errors():
    settings.verify_ssl_certs = False
    disable_warnings(InsecureRequestWarning)


def _create_handlers(args):
    handlers = FileEventHandlers()
    error_logger = common.get_error_logger()
    settings.global_exception_message_receiver = error_logger.error
    handlers.handle_error = error_logger.error
    output_format = args.output_format
    logger_formatter = _get_log_formatter(output_format)
    logger = _get_logger(
        formatter=logger_formatter,
        destination=args.destination,
        destination_type=args.destination_type,
        destination_port=int(args.destination_port),
        destination_protocol=args.destination_protocol,
    )
    handlers.handle_response = _get_response_handler(logger)
    return handlers


def _get_logger(
    formatter, destination, destination_type, destination_port=514, destination_protocol="TCP"
):
    try:
        return common.get_logger(
            formatter=formatter,
            destination=destination,
            destination_type=destination_type,
            destination_port=destination_port,
            destination_protocol=destination_protocol,
        )
    except (AttributeError, gaierror):
        print(
            "Error with provided server destination arguments: hostname={0}, port={1}, protocol={2}.".format(
                destination, destination_port, destination_protocol
            )
        )
        exit(1)
    except IOError:
        print("Error with provided file path {0}. Try --dest path/to/file.".format(destination))
        exit(1)


def _set_up_cursor_store(record_cursor, clear_cursor, handlers):
    if record_cursor or clear_cursor:
        store = AEDCursorStore()
        if clear_cursor:
            store.reset()

        if record_cursor:
            handlers.record_cursor_position = store.replace_stored_insertion_timestamp
            handlers.get_cursor_position = store.get_stored_insertion_timestamp
            return store


def _get_log_formatter(output_format):
    if output_format == "JSON":
        return AEDDictToJSONFormatter()
    elif output_format == "CEF":
        return AEDDictToCEFFormatter()
    else:
        print("Unsupported output format {0}".format(output_format))
        exit(1)


def _get_response_handler(logger):
    def handle_response(response):
        response_dict = json.loads(response.text)
        file_events_key = u"fileEvents"
        if file_events_key in response_dict:
            events = response_dict[file_events_key]
            for event in events:
                logger.info(event)

    return handle_response


def _create_sdk_from_args(args, handlers):
    server = _get_server_from_args(args)
    username = _get_username_from_args(args)
    password = _get_password(username)
    try:
        sdk = SDK.create_using_local_account(
            host_address=server, username=username, password=password
        )
        return sdk
    except Exception as ex:
        handlers.handle_error(ex)
        print("Incorrect username or password.")
        exit(1)


def _get_server_from_args(args):
    server = args.c42_authority_url
    if server is None:
        _exit_from_argument_error("Host address not provided.", args.cli_parser)

    return server


def _get_username_from_args(args):
    username = args.c42_username
    if username is None:
        _exit_from_argument_error("Username not provided.", args.cli_parser)

    return username


def _exit_from_argument_error(message, parser):
    print(message)
    parser.print_usage()
    exit(1)


def _get_password(username):
    password = keyring.get_password(_SERVICE_NAME_FOR_KEYCHAIN, username)
    if password is None:
        try:
            password = getpass.getpass(prompt="Code42 password: ")
            save_password = common.get_input("Save password to keychain? (y/n): ")
            if save_password.lower()[0] == "y":
                keyring.set_password(_SERVICE_NAME_FOR_KEYCHAIN, username, password)

        except KeyboardInterrupt:
            print()
            exit(1)

    return password


def _extract(args, sdk, handlers):
    min_timestamp = _parse_min_timestamp(args.begin_date)
    max_timestamp = common.parse_timestamp(args.end_date)
    extractor = AEDEventExtractor(sdk, handlers)
    extractor.extract(min_timestamp, max_timestamp, args.exposure_types)


def _parse_min_timestamp(begin_date):
    min_timestamp = common.parse_timestamp(begin_date)
    boundary_date = datetime.utcnow() - timedelta(days=90)
    boundary = convert_datetime_to_timestamp(boundary_date)
    if min_timestamp < boundary:
        print("Argument '--begin' must be within 90 days.")
        exit(1)

    return min_timestamp


if __name__ == "__main__":
    main()

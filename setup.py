from setuptools import find_packages, setup

setup(
    name="c42seceventcli",
    version="0.1.0",
    description="CLI for retrieving Code42 Exfiltration Detection events",
    packages=find_packages(include=["c42seceventcli", "c42seceventcli.*"]),
    python_requires=">=2.7, !=3.0.*, !=3.1.*, !=3.2.*, !=3.3.*, !=3.4.*, <4",
    install_requires=["c42secevents", "urllib3", "keyring"],
    license="MIT",
    include_package_data=True,
    zip_safe=False,
    extras_require={"dev": ["pre-commit==1.18.3", "pytest==4.6.5", "pytest-mock==1.10.4"]},
    entry_points={
        "console_scripts": ["extract-aed=c42seceventcli.aed.command_line:main"]
    }
)

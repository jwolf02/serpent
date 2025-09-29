from setuptools import setup

setup(
    name="serpent",
    version="1.0",
    install_requires=["pyserial", "termcolor"],
    py_modules=["serpent"],
    entry_points={
        "console_scripts": [
            "serpent=serpent:main",
        ],
    },
)

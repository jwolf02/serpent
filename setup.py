from setuptools import setup

setup(
    name="serpent",
    version="1.0.6",
    install_requires=["pyserial"],
    py_modules=["serpent"],
    entry_points={
        "console_scripts": [
            "serpent=serpent:main",
        ],
    },
)

"""
Setup script for the Modular Trading System
"""

from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

with open("requirements.txt", "r", encoding="utf-8") as fh:
    requirements = [line.strip() for line in fh if line.strip() and not line.startswith("#")]

setup(
    name="modular-trading-system",
    version="1.0.0",
    author="Trading System Developer",
    author_email="developer@example.com",
    description="A modular Python trading system for Interactive Brokers and other brokers",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/yourusername/modular-trading-system",
    packages=find_packages(),
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Financial and Insurance Industry",
        "Topic :: Office/Business :: Financial :: Investment",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
    ],
    python_requires=">=3.7",
    install_requires=requirements,
    extras_require={
        "dev": [
            "pytest>=6.0.0",
            "jupyter>=1.0.0",
            "matplotlib>=3.5.0",
        ],
        "ta": [
            "ta-lib>=0.4.0",
        ],
    },
    entry_points={
        "console_scripts": [
            "trading-system-example=example_usage:main",
            "trading-strategy-example=strategy_example:main",
        ],
    },
    include_package_data=True,
    package_data={
        "trading_system": ["config/*.json"],
    },
)
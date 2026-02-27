"""
Setup script for multicam-common Python package.
"""

from setuptools import setup, find_packages
from pathlib import Path

# Read the README file
this_directory = Path(__file__).parent
long_description = (this_directory / "README.md").read_text() if (this_directory / "README.md").exists() else ""

setup(
    name="multicam-common",
    version="1.1.0",
    author="MultiCam Team",
    description="Shared types and constants for MultiCam synchronized recording API",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/yourusername/multiCamCommon",
    packages=find_packages(),
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "Topic :: Software Development :: Libraries :: Python Modules",
        "Topic :: Multimedia :: Video",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Programming Language :: Python :: 3.13",
    ],
    python_requires=">=3.8",
    install_requires=[
        # No external dependencies - pure Python
    ],
    extras_require={
        "dev": [
            "pytest>=7.0",
            "pytest-cov>=4.0",
            "black>=23.0",
            "mypy>=1.0",
        ],
    },
    keywords="multicam video recording synchronization api",
    project_urls={
        "Bug Reports": "https://github.com/yourusername/multiCamCommon/issues",
        "Source": "https://github.com/yourusername/multiCamCommon",
        "Documentation": "https://github.com/yourusername/multiCamCommon/blob/main/README.md",
    },
)

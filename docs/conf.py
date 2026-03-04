"""Sphinx configuration for reeln documentation."""

from __future__ import annotations

import importlib.metadata
from pathlib import Path

# -- Project information -----------------------------------------------------

project = "reeln"
author = "Streamn Dad"
copyright = "2026, Streamn Dad"

# Read version from installed package or fallback to __init__.py
try:
    release = importlib.metadata.version("reeln")
except importlib.metadata.PackageNotFoundError:
    # Fallback: read from source when package isn't installed (e.g. RTD build)
    _init = Path(__file__).resolve().parent.parent / "reeln" / "__init__.py"
    for _line in _init.read_text().splitlines():
        if _line.startswith("__version__"):
            release = _line.split('"')[1]
            break
    else:
        release = "0.0.0"

version = ".".join(release.split(".")[:2])

# -- General configuration ---------------------------------------------------

extensions = [
    "myst_parser",
    "sphinx.ext.autodoc",
    "sphinx.ext.intersphinx",
    "sphinx_copybutton",
]

# MyST settings
myst_enable_extensions = [
    "colon_fence",
    "deflist",
    "fieldlist",
]
myst_heading_anchors = 3

# Source settings
source_suffix = {
    ".md": "markdown",
    ".rst": "restructuredtext",
}
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]

# -- Intersphinx mapping ----------------------------------------------------

intersphinx_mapping = {
    "python": ("https://docs.python.org/3", None),
}

# -- HTML output -------------------------------------------------------------

html_theme = "furo"
html_title = "reeln"
html_theme_options = {
    "source_repository": "https://github.com/StreamnDad/reeln-cli",
    "source_branch": "main",
    "source_directory": "docs/",
}

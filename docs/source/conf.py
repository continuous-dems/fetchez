# Configuration file for the Sphinx documentation builder.
#
# For the full list of built-in configuration values, see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html

# -- Project information -----------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#project-information

import os
import sys

sys.path.insert(0, os.path.abspath("../.."))
sys.path.insert(0, os.path.abspath("../_ext"))

project = "Fetchez"
copyright = "2026, Matthew Love"
author = "Matthew Love"
release = "0.3.0"

# -- General configuration ---------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#general-configuration

extensions = [
    "sphinx.ext.autodoc",  # Generate docs from docstrings
    "sphinx.ext.napoleon",  # Support Google-style docstrings
    "sphinx.ext.viewcode",  # Add links to source code
    "sphinx.ext.githubpages",  # Auto-generate .nojekyll for GH Pages
    "myst_parser",  # Parse Markdown files
    "module_table",  # Generate module catalog table
]

napoleon_google_docstring = True
napoleon_numpy_docstring = False
napoleon_include_init_with_doc = False

# # MyST Parser configuration
# source_suffix = {
#     '.rst': 'restructuredtext',
#     '.txt': 'markdown',
#     '.md': 'markdown',
# }

templates_path = ["_templates"]
exclude_patterns = []

# -- Options for HTML output -------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#options-for-html-output

# html_theme = 'sphinx_rtd_theme'
# html_theme = 'alabaster'
html_theme = "pydata_sphinx_theme"
html_static_path = ["_static"]

html_sidebars = {"**": []}

html_theme_options = {
    "github_url": "https://github.com/ciresdem/fetchez",
    "show_prev_next": False,
    "navbar_end": ["theme-switcher", "navbar-icon-links"],
    # "secondary_sidebar_items": ["page-toc", "edit-this-page", "sourcelink"],
    "secondary_sidebar_items": [],
    "footer_items": ["copyright", "sphinx-version", "theme-version"],
}

# Optional: Add a logo
# html_logo = "_static/logo.png"

# -- Autodoc Options ---------------------------------------------------------
# Ensure methods are documented
autodoc_default_options = {
    "members": True,
    "member-order": "bysource",
    "special-members": "__init__",
    "undoc-members": True,
    "exclude-members": "__weakref__",
}

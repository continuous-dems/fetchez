# Configuration file for the Sphinx documentation builder.
#
# For the full list of built-in configuration values, see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html

# -- Project information -----------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#project-information

import os, sys

sys.path.insert(0, os.path.abspath('../..'))

project = 'Fetchez'
copyright = '2026, Matthew Love'
author = 'Matthew Love'
release = '0.2.0'

# -- General configuration ---------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#general-configuration

extensions = [
    'sphinx.ext.autodoc',      # Generate docs from docstrings
    'sphinx.ext.napoleon',     # Support Google-style docstrings
    'sphinx.ext.viewcode',     # Add links to source code
    'sphinx.ext.githubpages',  # Auto-generate .nojekyll for GH Pages
    'myst_parser',             # Parse Markdown files
]

# MyST Parser configuration
source_suffix = {
    '.rst': 'restructuredtext',
    '.txt': 'markdown',
    '.md': 'markdown',
}

templates_path = ['_templates']
exclude_patterns = []



# -- Options for HTML output -------------------------------------------------
# https://www.sphinx-doc.org/en/master/usage/configuration.html#options-for-html-output

#html_theme = 'sphinx_rtd_theme'
html_theme = 'alabaster'
html_static_path = ['_static']

# Optional: Add a logo
# html_logo = "_static/logo.png"

# -- Autodoc Options ---------------------------------------------------------
# Ensure methods are documented
autodoc_default_options = {
    'members': True,
    'member-order': 'bysource',
    'special-members': '__init__',
    'undoc-members': True,
    'exclude-members': '__weakref__'
}

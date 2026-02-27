# -*- coding: utf-8 -*-

__author__ = "Matthew Love"
__credits__ = "CIRES"

try:
    from fetchez._version import __version__
except ImportError:
    # Fallback when using the package from source without installing
    # in editable mode with pip (nobody should do this):
    # <https://pip.pypa.io/en/stable/topics/local-project-installs/#editable-installs>
    import warnings

    warnings.warn(
        "Importing 'fetchez' outside a proper installation."
        " It's highly recommended to install the package from a stable release or"
        " in editable mode.",
        stacklevel=2,
    )
    __version__ = "dev"

# Import everything except the individual modules.
from . import fred
from . import core
from . import spatial
from . import registry
from .api import search, get

__all__ = ["core", "fred", "spatial", "registry", "search", "get"]

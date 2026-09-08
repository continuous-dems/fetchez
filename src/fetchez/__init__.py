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
from .api import (
    Pipeline,
    search,
    get,
    read,
    list_modules,
    search_modules,
    list_bundles,
    search_bundles,
    list_recipes,
    search_recipes,
    list_hooks,
    search_hooks,
    list_presets,
    search_presets,
    list_schemas,
    search_schemas,
    list_modifiers,
    search_modifiers,
    run_recipe,
)

__all__ = [
    "Pipeline",
    "core",
    "fred",
    "spatial",
    "registry",
    "search",
    "get",
    "read",
    "list_modules",
    "search_modules",
    "list_bundles",
    "search_bundles",
    "list_recipes",
    "search_recipes",
    "list_hooks",
    "search_hooks",
    "list_presets",
    "search_presets",
    "list_schemas",
    "search_schemas",
    "list_modifiers",
    "search_modifiers",
    "list_streams",
    "search_streams",
    "list_readers",
    "search_readers",
    "list_profiles",
    "search_profiles",
    "run_recipe",
    "__version__",
]

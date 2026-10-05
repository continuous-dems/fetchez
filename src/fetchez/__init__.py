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
from . import core, fred, registry, spatial
from .api import (
    Pipeline,
    get,
    list_bundles,
    list_hooks,
    list_modifiers,
    list_modules,
    list_presets,
    list_recipes,
    list_schemas,
    read,
    run_recipe,
    search,
    search_bundles,
    search_hooks,
    search_modifiers,
    search_modules,
    search_presets,
    search_recipes,
    search_schemas,
)

__all__ = [
    "Pipeline",
    "__version__",
    "core",
    "fred",
    "get",
    "list_bundles",
    "list_hooks",
    "list_modifiers",
    "list_modules",
    "list_presets",
    "list_profiles",
    "list_readers",
    "list_recipes",
    "list_schemas",
    "list_streams",
    "read",
    "registry",
    "run_recipe",
    "search",
    "search_bundles",
    "search_hooks",
    "search_modifiers",
    "search_modules",
    "search_presets",
    "search_profiles",
    "search_readers",
    "search_recipes",
    "search_schemas",
    "search_streams",
    "spatial",
]

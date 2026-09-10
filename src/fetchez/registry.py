#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
fetchez.registry
~~~~~~~~~~~~~~~~

A unified, dynamic registry system for discovering and loading
Fetchez Modules, Hooks, Schemas, and other plugins.

:copyright: (c) 2010-2026 Regents of the University of Colorado
:license: MIT, see LICENSE for more details.
"""

import os
import sys
import yaml
import copy
import pkgutil
import importlib
import importlib.util
import importlib.metadata
import importlib.resources
import inspect
import logging
from pathlib import Path
from typing import Dict, Any, Type, Optional, List

from fetchez.modules import FetchModule
from fetchez.hooks import FetchHook
from fetchez.recipes.modifiers import BaseModifier
from fetchez.recipes.schemas import BaseSchema
from fetchez.streams import BaseStream
from fetchez.streams.readers import BaseReader
from fetchez.utils import get_class_arguments

logger = logging.getLogger(__name__)


class PluginRegistry:
    """Base class for dynamically discovering and registering plugins."""

    _registry: Dict[str, Any]

    # These must be defined by the subclasses
    base_class: Optional[Type] = None
    builtin_pkg: str = ""
    entry_point_group: str = ""
    user_folder: str = ""

    @classmethod
    def get_registry(cls, clear_registry: bool = False) -> Dict[str, Any]:
        """Initialization of the class-level registry dictionary."""

        if not hasattr(cls, "_registry") or clear_registry:
            cls._registry = {}

        return cls._registry

    @classmethod
    def load_builtins(cls):
        """Recursively scan and load all built-in plugins."""

        registry = cls.get_registry(clear_registry=True)
        if registry:
            return

        try:
            builtin_module = importlib.import_module(cls.builtin_pkg)

            for _, modname, ispkg in pkgutil.walk_packages(
                path=builtin_module.__path__,
                prefix=builtin_module.__name__ + ".",
            ):
                if not ispkg:
                    try:
                        mod = importlib.import_module(modname)
                        cls._register_from_module(mod)
                    except Exception as e:
                        logger.warning(f"Failed to load built-in {modname}: {e}")
        except ImportError:
            logger.warning(f"Built-in package {cls.builtin_pkg} not found.")

    @classmethod
    def load_user_plugins(cls):
        """Scan local directories for user-provided plugins."""

        home = Path.home()

        search_dirs = [
            str(home / ".fetchez" / cls.user_folder),
            str(Path.cwd() / ".fetchez" / cls.user_folder),
        ]

        for p_dir in search_dirs:
            if not Path(p_dir).exists():
                continue

            for f in os.listdir(p_dir):
                if f.endswith(".py") and not f.startswith("_"):
                    filepath = Path(p_dir) / f
                    mod_name = f"fetchez_user_{cls.user_folder}_{f[:-3]}"

                    try:
                        spec = importlib.util.spec_from_file_location(
                            mod_name, str(filepath)
                        )
                        if spec and spec.loader:
                            mod = importlib.util.module_from_spec(spec)
                            sys.modules[mod_name] = mod
                            spec.loader.exec_module(mod)
                            cls._register_from_module(mod)
                    except Exception as e:
                        logger.warning(f"Failed to load user plugin {filepath}: {e}")

    @classmethod
    def load_installed_plugins(cls):
        """Load external pip-installed extensions via entry_points."""

        try:
            eps = importlib.metadata.entry_points(group=cls.entry_point_group)
            for ep in eps:
                plugin_module = ep.load()
                # Scan the loaded extension for submodules
                for _, modname, ispkg in pkgutil.walk_packages(
                    path=plugin_module.__path__,
                    prefix=plugin_module.__name__ + ".",
                ):
                    if not ispkg:
                        try:
                            mod = importlib.import_module(modname)
                            cls._register_from_module(mod)
                        except Exception as e:
                            logger.exception(
                                f"Failed to load external plugin {modname}: {e}"
                            )
        except Exception as e:
            logger.error(
                f"Error checking entry points for {cls.entry_point_group}: {e}"
            )

    @classmethod
    def load_all(cls):
        """Load all plugins: builtins, user plugins, and pip extensions."""

        cls.load_builtins()
        cls.load_user_plugins()
        cls.load_installed_plugins()

    load_fast = load_all  # temp in case we forgot to update any calls to the depreciated `load_fast`

    @classmethod
    def _register_from_module(cls, module, use_namespaces=False):
        """Inspect a module and dynamically extract its metadata."""

        registry = cls.get_registry()

        is_core = module.__name__.startswith(cls.builtin_pkg)
        is_local = module.__name__.startswith("fetchez_user_")

        prefix = ""
        if not is_core:
            if is_local:
                prefix = "local"
            else:
                # e.g., 'globato.modules.bato' -> 'globato'
                # prefix = ".".join(module.__name__.split(".")[:-1])
                prefix = module.__name__.split(".")[0]

        local_classes = [
            (name, obj)
            for name, obj in inspect.getmembers(module, inspect.isclass)
            if obj.__module__ == module.__name__
        ]
        for name, obj in local_classes:
            if issubclass(obj, cls.base_class) and obj is not cls.base_class:
                raw_mod_key = getattr(obj, "name", name.lower())
                base_name = getattr(cls.base_class, "name", None)
                if raw_mod_key == base_name:
                    continue

                # --- Plugin Namespaces ---
                mod_key = raw_mod_key
                if not is_core:
                    if not raw_mod_key.startswith(f"{prefix}.") and use_namespaces:
                        mod_key = f"{prefix}.{raw_mod_key}"

                    logger.debug(
                        f"🧩 Loaded external plugin: '{mod_key}' from {prefix}"
                    )

                    if raw_mod_key in registry and registry[raw_mod_key].get(
                        "import_path", ""
                    ).startswith("fetchez."):
                        mod_key = f"{prefix}.{raw_mod_key}"
                        logger.debug(
                            f"⚠️ Blocked plugin '{prefix}' from hijacking core module '{raw_mod_key}'. "
                            f"It has been safely sandboxed as '{mod_key}'."
                        )

                meta = {
                    "mod": module.__name__,
                    "cls": name,
                    "_class_obj": obj,
                    "aliases": obj.__dict__.get("meta_aliases", []),
                }

                # --- Metadata Extraction ---
                # Modules must define `meta_` atrributes
                for attr_name in dir(obj):
                    if attr_name.startswith("meta_"):
                        clean_key = attr_name.replace("meta_", "")
                        meta[clean_key] = getattr(obj, attr_name)

                # --- Fallbacks for the CLI ---
                meta.setdefault("category", "Generic")
                meta.setdefault("desc", "No description provided.")
                meta.setdefault("domain", "Universal (Files)")
                meta.setdefault("requires", "any")

                meta["import_path"] = f"{obj.__module__}.{obj.__name__}"

                if hasattr(module, "__file__") and module.__file__:
                    meta["file_path"] = module.__file__

                meta["cli_args"] = get_class_arguments(obj)

                registry[mod_key] = meta

                # --- Register the raw_key if it doesn't exist (for backward compatibility) ---
                # if not is_core and raw_mod_key not in registry:
                #    registry[raw_mod_key] = meta

                for alias in meta["aliases"]:
                    # registry[alias] = meta
                    alias_key = alias if is_core else f"{prefix}.{alias}"
                    registry[alias_key] = meta

                    if not is_core and alias not in registry:
                        registry[alias] = meta

    @classmethod
    def get_info(cls, mod_key: str) -> Dict[str, Any]:
        return cls.get_registry().get(mod_key, {})

    @classmethod
    def _get_class(cls, mod_key: str):
        meta = cls.get_registry().get(mod_key)
        return meta.get("_class_obj") if meta else None

    @classmethod
    def get_class(cls, name: str):
        """Returns the class if cached, or lazily imports it on demand."""

        meta = cls.get_registry().get(name)
        if not meta:
            return None

        if "import_path" in meta:
            mod_path, class_name = meta["import_path"].rsplit(".", 1)

            try:
                # Standard import for pip-installed and built-in modules
                module = importlib.import_module(mod_path)
            except ModuleNotFoundError:
                # Fallback for dynamic local user plugins
                file_path = meta.get("file_path")
                if file_path and Path(file_path).exists():
                    spec = importlib.util.spec_from_file_location(mod_path, file_path)
                    if spec and spec.loader:
                        module = importlib.util.module_from_spec(spec)
                        sys.modules[mod_path] = module
                        spec.loader.exec_module(module)
                    else:
                        return None
                else:
                    return None

            actual_cls = getattr(module, class_name)
            return actual_cls

        return None

    load_module = get_class  # alias for backward compatability

    @classmethod
    def list_all(cls) -> Dict[str, Any]:
        return cls.get_registry()

    @classmethod
    def search_modules(cls, term: str):
        """Search modules by name, description, agency, or tags."""

        term = term.lower()
        results = []

        for key, meta in cls.get_registry().items():
            if (
                term in key.lower()
                or term in meta.get("desc", "").lower()
                or term in meta.get("agency", "").lower()
                or any(term in tag.lower() for tag in meta.get("tags", []))
                or any(term in alias.lower() for alias in meta.get("aliases", ""))
            ):
                if key not in results:
                    results.append(key)

        return results


class YamlRegistry:
    """A registry for discovering and loading yaml configuration files (recipes and hook presets)."""

    _registry: Dict[str, Any]

    # These must be defined by the subclasses
    base_class: Optional[Type] = None
    builtin_pkg: str = ""
    entry_point_group: str = ""
    user_folder: str = ""

    @classmethod
    def get_registry(cls) -> Dict[str, Any]:

        if not hasattr(cls, "_registry"):
            cls._registry = {}

        return cls._registry

    @classmethod
    def load_all(cls):
        cls.get_registry()

        try:
            eps = importlib.metadata.entry_points(group=cls.entry_point_group)
        except TypeError:
            eps = importlib.metadata.entry_points().get(cls.entry_point_group, [])

        for ep in eps:
            pkg_name = ep.value
            prefix = pkg_name.split(".")[0].lower()
            try:
                for file_path in importlib.resources.files(pkg_name).iterdir():
                    if file_path.name.endswith((".yaml", ".yml")):
                        cls._register_yaml(
                            prefix,
                            file_path.read_text(encoding="utf-8"),
                            str(file_path),
                        )
            except Exception as e:
                logger.warning(f"Failed to load yamls from package {pkg_name}: {e}")

        builtin_module = importlib.import_module(cls.builtin_pkg)
        builtin_path = builtin_module.__path__
        home_dir = Path.home() / ".fetchez" / cls.user_folder
        builtin_path.append(home_dir)
        for fdir in builtin_path:
            if Path(fdir).exists():
                for fn in os.listdir(fdir):
                    if fn.endswith((".yaml", ".yml")):
                        try:
                            f_dir = Path(fdir) / fn
                            with open(f_dir, "r", encoding="utf-8") as f:
                                cls._register_yaml("fetchez", f.read(), f_dir)
                        except Exception as e:
                            logger.warning(f"Failed to load yaml {fn}: {e}")

    load_fast = load_all  # temp for lingering load_fast calls

    @classmethod
    def _register_yaml(cls, provider, yaml_content: str, file_path: str):
        registry = cls.get_registry()

        try:
            config = yaml.safe_load(yaml_content)
            if not config:
                return

            if "name" in config:
                registry[config["name"]] = config
            config["provider"] = provider
        except Exception as e:
            logger.debug(f"Failed to parse YAML {file_path}: {e}")

    @classmethod
    def get_yaml(cls, name: str) -> Optional[Dict[str, Any]]:
        return cls.get_registry().get(name)

    # Temporary for backwards compatibility
    get_preset = get_yaml
    get_recipe = get_yaml


# =============================================================================
# The Registries
# =============================================================================
class ModuleRegistry(PluginRegistry):
    base_class = FetchModule
    builtin_pkg = "fetchez.modules"
    entry_point_group = "fetchez.modules"
    user_folder = "modules"


class HookRegistry(PluginRegistry):
    base_class = FetchHook
    builtin_pkg = "fetchez.hooks"
    entry_point_group = "fetchez.hooks"
    user_folder = "hooks"


# Modifiers modify recipes and Schemas validate them.
class ModifierRegistry(PluginRegistry):
    base_class = BaseModifier
    builtin_pkg = "fetchez.recipes.modifiers"
    entry_point_group = "fetchez.recipes.modifiers"
    user_folder = "recipes/modifiers"


class SchemaRegistry(PluginRegistry):
    base_class = BaseSchema
    builtin_pkg = "fetchez.recipes.schemas"
    entry_point_group = "fetchez.recipes.schemas"
    user_folder = "recipes/schemas"


class StreamRegistry(PluginRegistry):
    base_class = BaseStream
    builtin_pkg = "fetchez.streams"
    entry_point_group = "fetchez.streams"
    user_folder = "streams"


class ReaderRegistry(PluginRegistry):
    base_class = BaseReader
    builtin_pkg = "fetchez.streams.readers"
    entry_point_group = "fetchez.streams.readers"
    user_folder = "streams/readers"

    @classmethod
    def get_reader(cls, src, term: str, region=None, **kwargs):
        ProfileRegistry.load_all()
        if term:
            profile = ProfileRegistry.get_yaml(term)
            if profile:
                logger.debug(f"Using reader-profile {profile}")
                profile_reader = profile.get("reader", {})
                reader_name = profile_reader.get("name", "")
                reader = cls.get_class(reader_name)
                if reader:
                    profile_args = profile_reader.get("args", {})
                    return reader(src, region=region, **profile_args, **kwargs)
            else:
                logger.debug(f"No reader profile found, checking `{term}` data-type")
                reader = cls.get_reader_for_dtype(term)
                if reader:
                    logger.debug(f"Found `{reader.name}` for data-type: `{term}`")
                    return reader(src, region=region, **kwargs)

        _ext = src.split(".")[-1]
        logger.debug(f"No reader dtype found, checking `{_ext}` in extensions")
        reader = cls.get_reader_for_ext(_ext)
        if reader:
            return reader(src, region=region, **kwargs)

        return None

    @classmethod
    def get_reader_for_ext(cls, ext: str):
        """Iterate through registered readers to find one that supports this extension."""

        for name, meta in cls.get_registry().items():
            if ext.lower() in meta.get("extensions", []):
                return cls.get_class(name)
        return None

    @classmethod
    def get_reader_for_dtype(cls, dtype: str):
        """Find reader by exact dtype match."""

        for name, meta in cls.get_registry().items():
            target_dtype = meta.get("dtype", "")

            if isinstance(target_dtype, str):
                if dtype.lower() == target_dtype.lower():
                    return cls.get_class(name)
            elif isinstance(target_dtype, list):
                if dtype.lower() in [t.lower() for t in target_dtype]:
                    return cls.get_class(name)

        return None


class RecipeRegistry(YamlRegistry):
    """A registry for discovering and loading YAML recipes."""

    # _registry = {}
    builtin_pkg = "fetchez.recipes"
    entry_point_group = "fetchez.recipes"
    user_folder = "recipes"

    @classmethod
    def _register_yaml(cls, provider, yaml_content: str, file_path: str):
        registry = cls.get_registry()

        try:
            config = yaml.safe_load(yaml_content)
            if not config or "project" not in config:
                return

            # Use the project name from the YAML, fallback to the filename
            name = config["project"].get(
                "name", Path(file_path).name.replace(".yaml", "")
            )
            desc = config["project"].get("description", "No description available.")
            tags = config["project"].get("tags", [])

            registry[name] = {
                "name": name,
                "desc": desc,
                "config": config,
                "path": file_path,
                "tags": tags,
                "provider": provider,
            }
        except Exception as e:
            logger.debug(f"Failed to parse recipe YAML {file_path}: {e}")


# Presets extend Hooks
class PresetRegistry(YamlRegistry):
    builtin_pkg = "fetchez.hooks.presets"
    entry_point_group = "fetchez.hooks.presets"
    user_folder = "hooks/presets"

    @classmethod
    def _register_yaml(cls, provider, yaml_content: str, file_path: str):
        registry = cls.get_registry()

        try:
            config = yaml.safe_load(yaml_content)
            if not config:
                return

            if "presets" in config:
                for p_name, p_def in config.get("presets", {}).items():
                    p_def["provider"] = provider
                    registry[p_name] = p_def
            else:
                if "name" in config and "hooks" in config:
                    config["provider"] = provider
                    registry[config["name"]] = config
        except Exception as e:
            logger.debug(f"Failed to parse preset YAML {file_path}: {e}")

    @classmethod
    def expand_hooks(
        cls,
        hook_defs: List[Dict[str, Any]],
        parent_hooks: Optional[List[Dict[str, Any]]] = None,
    ) -> List[Dict[str, Any]]:
        """Recursively expands preset references in a list of hook definitions into a flat list of hook dictionary configs."""

        cls.load_all()
        expanded_list = []
        parent_hooks = parent_hooks or []

        for h in hook_defs:
            if isinstance(h, str):
                h = {"name": h}

            h = copy.deepcopy(h)
            name = h.get("name")
            is_preset = h.get("preset")

            if parent_hooks and name:
                # Convert parent_hooks (list) into a map for fast lookup
                hook_map = {
                    hook.get("name"): hook
                    for hook in parent_hooks
                    if isinstance(hook, dict) and "name" in hook
                }
                if name in hook_map:
                    h_args = h.get("args", {}).copy()
                    h_args.update(hook_map[name].get("args", {}))
                    h["args"] = h_args

            if is_preset:
                user_args = h.get("args", [])
                if isinstance(user_args, dict):
                    # Convert dict format to list-of-dicts if user passed it that way
                    user_args = [
                        {"name": k, "args": v.get("args", v)}
                        for k, v in user_args.items()
                    ]

                preset_def = cls.get_yaml(is_preset)

                if preset_def:
                    preset_hooks = copy.deepcopy(preset_def.get("hooks", []))

                    # Merge user_args and parent_hooks to pass down the chain
                    combined_overrides = copy.deepcopy(parent_hooks)
                    for u_arg in user_args:
                        u_name = u_arg.get("name")
                        existing = next(
                            (p for p in combined_overrides if p.get("name") == u_name),
                            None,
                        )
                        if existing:
                            existing.setdefault("args", {}).update(
                                u_arg.get("args", {})
                            )
                        else:
                            combined_overrides.append(u_arg)

                    expanded_child_hooks = cls.expand_hooks(
                        preset_hooks, parent_hooks=combined_overrides
                    )
                    expanded_list.extend(expanded_child_hooks)
                else:
                    logger.error(f"Preset '{is_preset}' not found in registry.")
            else:
                expanded_list.append(h)

        return expanded_list

    @classmethod
    def hook_list_from_preset(cls, preset_def_or_name: Any) -> List[Any]:
        """Convert a preset name or dictionary into an expanded list of instantiated Hook objects."""

        from .registry import HookRegistry

        if isinstance(preset_def_or_name, str):
            hook_defs = cls.expand_hooks([{"preset": preset_def_or_name}])
        elif isinstance(preset_def_or_name, dict):
            raw_hooks = preset_def_or_name.get("hooks", [])
            hook_defs = cls.expand_hooks(raw_hooks)
        else:
            return []

        HookRegistry.load_all()
        hooks = []
        for h_def in hook_defs:
            name = h_def.get("name")
            kwargs = h_def.get("args", {})

            hook_cls = HookRegistry.get_class(str(name))
            if hook_cls:
                try:
                    hooks.append(hook_cls(**kwargs))
                except Exception as e:
                    logger.error(f"Failed to init hook '{name}' from preset: {e}")
            else:
                logger.warning(f"Hook '{name}' not found in registry.")

        return hooks


# Bundles extend Modules
class BundleRegistry(YamlRegistry):
    """A registry for discovering and loading Module Bundles (Data Packages)."""

    builtin_pkg = "fetchez.modules.bundles"
    entry_point_group = "fetchez.modules.bundles"
    user_folder = "modules/bundles"

    @staticmethod
    def get_module_signature(mod_dict: Any) -> str:
        """Creates a unique signature for a module configuration to allow deduplication."""

        if isinstance(mod_dict, str):
            return mod_dict

        m_name = mod_dict.get("module")
        if not m_name:
            return str(mod_dict)

        args = mod_dict.get("args", {})
        ids = [
            f"{key}={args[key]}"
            for key in [
                "datatype",
                "dataset",
                "datasets",
                "formats",
                "layer",
                "product",
                "survey_id",
                "url",
                "path",
            ]
            if key in args
        ]

        return f"{m_name}::" + "::".join(sorted(ids)) if ids else m_name

    @classmethod
    def expand_modules(
        cls, raw_modules: List[Any], parent_weight: float = 1.0
    ) -> List[Dict[str, Any]]:
        """Recursively flattens bundles/recipes, calculates stacked weights, and deduplicates/merges modules."""

        cls.load_all()
        ModuleRegistry.load_all()
        BundleRegistry.load_all()
        RecipeRegistry.load_all()
        PresetRegistry.load_all()

        expanded_dict: dict[str, Any] = {}

        for mod_dict in raw_modules:
            if isinstance(mod_dict, str):
                bundle_def = cls.get_yaml(mod_dict)
                if bundle_def:
                    mod_dict = {"bundle": mod_dict}
                else:
                    expanded_dict[mod_dict] = {"module": mod_dict}
                    continue

            target = mod_dict.get("bundle") or mod_dict.get("recipe")
            if target:
                user_args = mod_dict.get("args", {})
                user_hooks = mod_dict.get("hooks", [])
                current_weight = float(user_args.get("weight", 1.0)) * parent_weight

                bundle_def = cls.get_yaml(target)
                if not bundle_def:
                    recipe_meta = RecipeRegistry.get_yaml(target)
                    if recipe_meta:
                        bundle_def = recipe_meta.get("config", {})

                if bundle_def:
                    child_modules = copy.deepcopy(bundle_def.get("modules", []))
                    products = bundle_def.get("products")
                    selected = user_args.get("products")
                    if products:
                        unknown_args = set(user_args).difference({"products", "weight"})
                        if unknown_args:
                            raise ValueError(
                                f"Unknown bundle argument(s): {', '.join(sorted(unknown_args))}. "
                                "Use products=s1m/1m/1_as in source strings."
                            )
                    if products and selected and str(selected).lower() != "all":
                        selected_products = {
                            value.strip()
                            for value in str(selected).replace(",", "/").split("/")
                            if value.strip()
                        }
                        unknown = selected_products.difference(products)
                        if unknown:
                            raise ValueError(
                                f"Unknown product(s) for {target}: "
                                f"{', '.join(sorted(unknown))}"
                            )
                        child_modules = [
                            child
                            for child in child_modules
                            if child.get("args", {}).get("datasets")
                            in selected_products
                        ]
                    start_hook = bundle_def.get("product_start_hook")
                    if products and child_modules and start_hook:
                        for hook in child_modules[0].get("hooks", []):
                            if hook.get("name") == start_hook:
                                hook.setdefault("args", {})["start"] = True
                                break
                    child_expanded = cls.expand_modules(child_modules, current_weight)

                    for child_mod in child_expanded:
                        if user_hooks:
                            child_mod["hooks"] = PresetRegistry.expand_hooks(
                                child_mod.get("hooks", []), user_hooks
                            )

                        sig = cls.get_module_signature(child_mod)
                        expanded_dict[sig] = child_mod

            elif "module" in mod_dict:
                sig = cls.get_module_signature(mod_dict)

                args = mod_dict.get("args", {}).copy()
                local_weight = float(args.get("weight", 1.0))
                args["weight"] = local_weight * parent_weight
                mod_dict["args"] = args

                if sig in expanded_dict and isinstance(expanded_dict[sig], dict):
                    existing = expanded_dict[sig]
                    merged_args = existing.get("args", {}).copy()
                    merged_args.update(mod_dict.get("args", {}))
                    merged_hooks = mod_dict.get("hooks", existing.get("hooks", []))

                    expanded_dict[sig] = {
                        "module": mod_dict["module"],
                        "args": merged_args,
                        "hooks": merged_hooks,
                    }
                else:
                    expanded_dict[sig] = mod_dict
            else:
                logger.error(f"Invalid module definition: {mod_dict}")

        return list(expanded_dict.values())


# Profiles extend Streams
class ProfileRegistry(YamlRegistry):
    """A registry for discovering and loading Format Profilesx."""

    builtin_pkg = "fetchez.streams.profiles"
    entry_point_group = "fetchez.streams.profiles"
    user_folder = "streams/profiles"

    # @classmethod
    # def reader_args_from_profile(cls, profile_def):
    #     """Convert yaml definition to list of Hook Objects."""

    #     readers = {}
    #     profile_id = profile_def.get("profile")
    #     for p_def in profile_def.get("reader", []):
    #         name = p_def.get("name")
    #         kwargs = p_def.get("args", {})
    #         readers[name] = kwargs
    #     return readers


# =============================================================================
# Old YAML Registries (recipe & preset)
# =============================================================================
class _RecipeRegistry:
    """A registry for discovering and loading YAML recipes."""

    _registry: Dict[str, Any]

    entry_point_group = "fetchez.recipes"
    user_folder = "recipes"

    @classmethod
    def get_registry(cls) -> Dict[str, Any]:
        """Initialization of the class-level registry dictionary."""

        if not hasattr(cls, "_registry"):
            cls._registry = {}

        return cls._registry

    # @classmethod
    # def get_registry(cls) -> Dict[str, Any]:
    #     return cls._registry

    @classmethod
    def load_all(cls):

        cls.get_registry()
        # if cls._registry:
        #     return

        try:
            eps = importlib.metadata.entry_points(group=cls.entry_point_group)
        except TypeError:
            eps = importlib.metadata.entry_points().get(cls.entry_point_group, [])

        for ep in eps:
            pkg_name = ep.value
            try:
                for file_path in importlib.resources.files(pkg_name).iterdir():
                    if file_path.name.endswith((".yaml", ".yml")):
                        cls._register_yaml(
                            file_path.read_text(encoding="utf-8"), str(file_path)
                        )
            except Exception as e:
                logger.warning(f"Failed to load recipes from package {pkg_name}: {e}")

        home_dir = Path(f"~/.fetchez/{cls.user_folder}").expanduser()
        if home_dir.exists():
            for fn in os.listdir(home_dir):
                if fn.endswith((".yaml", ".yml")):
                    try:
                        home_fn = home_dir / fn
                        with open(home_fn, "r", encoding="utf-8") as f:
                            cls._register_yaml(f.read(), home_fn)
                    except Exception as e:
                        logger.warning(f"Failed to load local recipe {fn}: {e}")

    @classmethod
    def _register_yaml(cls, yaml_content: str, file_path: str):
        registry = cls.get_registry()

        try:
            config = yaml.safe_load(yaml_content)
            if not config or "project" not in config:
                return

            # Use the project name from the YAML, fallback to the filename
            name = config["project"].get(
                "name", Path(file_path).name.replace(".yaml", "")
            )
            desc = config["project"].get("description", "No description available.")

            registry[name] = {
                "name": name,
                "desc": desc,
                "config": config,
                "path": file_path,
            }
        except Exception as e:
            logger.debug(f"Failed to parse recipe YAML {file_path}: {e}")

    @classmethod
    def get_recipe(cls, name: str) -> Optional[Dict[str, Any]]:
        registry = cls.get_registry()
        return registry.get(name)


class _PresetRegistry:
    """A registry for discovering and loading hook Presets (Macros)."""

    _registry: Dict[str, Any]

    builtin_pkg = "fetchez.presets"
    entry_point_group = "fetchez.presets"
    user_folder = "presets"

    @classmethod
    def get_registry(cls) -> Dict[str, Any]:

        if not hasattr(cls, "_registry"):
            cls._registry = {}
        return cls._registry

    @classmethod
    def load_all(cls):
        cls.get_registry()

        try:
            eps = importlib.metadata.entry_points(group=cls.entry_point_group)
        except TypeError:
            eps = importlib.metadata.entry_points().get(cls.entry_point_group, [])

        for ep in eps:
            pkg_name = ep.value
            try:
                for file_path in importlib.resources.files(pkg_name).iterdir():
                    if file_path.name.endswith((".yaml", ".yml")):
                        cls._register_yaml(
                            file_path.read_text(encoding="utf-8"), str(file_path)
                        )
            except Exception as e:
                logger.warning(f"Failed to load presets from package {pkg_name}: {e}")

        builtin_module = importlib.import_module(cls.builtin_pkg)
        builtin_path = builtin_module.__path__
        home_dir = Path(f"~/.fetchez/{cls.user_folder}").expanduser()
        builtin_path.append(home_dir)
        for fdir in builtin_path:
            if Path(fdir).exists():
                for fn in os.listdir(fdir):
                    if fn.endswith((".yaml", ".yml")):
                        try:
                            f_fn = Path(fdir) / fn
                            with open(f_fn, "r", encoding="utf-8") as f:
                                cls._register_yaml(f.read(), f_fn)
                        except Exception as e:
                            logger.warning(f"Failed to load preset {fn}: {e}")

        legacy_file = Path("~/.fetchez/presets.yaml").expanduser()
        if legacy_file.exists():
            try:
                with open(legacy_file, "r", encoding="utf-8") as f:
                    cls._register_yaml(f.read(), legacy_file, is_legacy=True)
            except Exception:
                pass

    @classmethod
    def _register_yaml(cls, yaml_content: str, file_path: str, is_legacy=False):
        registry = cls.get_registry()

        try:
            config = yaml.safe_load(yaml_content)
            if not config:
                return

            if is_legacy or "presets" in config:
                for p_name, p_def in config.get("presets", {}).items():
                    registry[p_name] = p_def
            else:
                if "name" in config and "hooks" in config:
                    registry[config["name"]] = config
        except Exception as e:
            logger.debug(f"Failed to parse preset YAML {file_path}: {e}")

    @classmethod
    def get_preset(cls, name: str) -> Optional[Dict[str, Any]]:
        return cls.get_registry().get(name)

    @classmethod
    def hook_list_from_preset(cls, preset_def):
        """Convert yaml definition to list of Hook Objects."""

        hooks = []
        for h_def in preset_def.get("hooks", []):
            name = h_def.get("name")
            kwargs = h_def.get("args", {})

            hook_cls = HookRegistry.get_class(name)
            if hook_cls:
                try:
                    hooks.append(hook_cls(**kwargs))
                except Exception as exception:
                    logger.error(f"Failed to init preset hook '{name}': {exception}")
            else:
                logger.warning(f"Preset hook '{name}' not found.")

        return hooks

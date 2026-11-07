#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
fetchez.utils.parsing
~~~~~~~~~~~~~~~~

Utility functions for common Fetchez parsing.

:copyright: (c) 2012 - 2026 CIRES Coastal DEM Team
:license: MIT, see LICENSE for more details.
"""

import logging
import shutil
import re
import inspect
from pathlib import Path
from typing import Optional, Dict, Any, List


from .logging import colorize, CYAN, RED

logger = logging.getLogger(__name__)


# =============================================================================
# Factory Module parsing (from cudem)
# =============================================================================
def _parse_value_string(val_str: str) -> Any:
    """Helper to parse string values into Python types (bool, None, list)."""

    val_lower = val_str.lower()
    # if utils.str2bool(val_str) is not None:
    #     return utils.str2bool(val_str)
    if val_lower == "false":
        return False
    elif val_lower == "true":
        return True
    elif val_lower == "none":
        return None
    elif ";" in val_str:
        return val_str.strip('"').split(";")
    else:
        return val_str.strip('"')


def parse_fmod(fmod):
    """Parse a factory module string.

    Returns:
        Tuple containing (all_options, module_name, module_arguments)
    """

    opts = fmod2dict(fmod)
    mod = opts.get("_module")
    mod_args = {k: v for k, v in opts.items() if k != "_module"}
    return opts, mod, mod_args


def parse_fmod_argparse(fmod):
    """Parse a factory module string.

    Returns:
        Tuple containing (all_options, module_name, module_arguments)
    """

    opts = fmod2dict(fmod)
    mod = opts.get("_module")
    mod_args = {k: v for k, v in opts.items() if k != "_module"}
    mod_args = [f"--{k}={v}" for k, v in opts.items() if k != "_module"]
    return opts, mod, mod_args


def fmod2dict(fmod: str, dict_args: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Convert factory module string to a dict.

    Args:
      fmod (str): A factory module string.
      dict_args (dict, optional): A dict to append to.

    Returns:
      dict: A dictionary of the key/values.
    """

    if dict_args is None:
        dict_args = {}

    ## Split by colon, ignoring colons inside quotes
    args_list = re.split(r':(?=(?:[^"]*"[^"]*")*[^"]*$)', fmod)

    for arg in args_list:
        ## Split by equals, ignoring equals inside quotes
        p_arg = re.split(r'=(?=(?:[^"]*"[^"]*")*[^"]*$)', arg)

        if len(p_arg) == 1:
            if "_module" not in dict_args:
                dict_args["_module"] = p_arg[0]
        elif len(p_arg) > 1:
            key = p_arg[0]
            val_str = p_arg[1]

            ## If there are multiple '=' parts, rejoin the rest
            if len(p_arg) > 2:
                dict_args[key] = "=".join(p_arg[1:])
            else:
                dict_args[key] = _parse_value_string(val_str)

    return dict_args


def parse_arg_to_list(val, cast_type):
    """Parse a CLI string or existing list into a typed list.

    Expects CLI format: 'val1/val2'
    """

    if val is None:
        return []
    if isinstance(val, list):
        return [cast_type(v) for v in val]
    if isinstance(val, str) and "/" in val:
        return [cast_type(v) for v in val.split("/")]
    return [cast_type(val)]


def parse_arg_to_dict(val, cast_type=str):
    """Parse a CLI string or existing dictionary into a typed dictionary.

    Expects CLI format: 'key1=val1/key2=val2'
    """

    if val is None:
        return {}

    if isinstance(val, dict):
        return {str(k).strip(): cast_type(v) for k, v in val.items()}

    out_dict = {}
    if isinstance(val, str):
        val = val.strip()

        # JSON
        if val.startswith("{") and val.endswith("}"):
            try:
                import json

                parsed = json.loads(val)
                return {str(k).strip(): cast_type(v) for k, v in parsed.items()}
            except Exception as e:
                logger.debug(f"Failed to parse {val} as json: {e}")

        # String
        pairs = val.split("/")
        for pair in pairs:
            if not pair.strip():
                continue

            if "=" in pair:
                k, v = pair.split("=", 1)
            # Fallback to ':' if users try that instead
            elif ":" in pair:
                k, v = pair.split(":", 1)
            else:
                k, v = pair, True

            try:
                out_dict[str(k).strip()] = cast_type(v)
            except Exception:
                out_dict[str(k).strip()] = v

    return out_dict


def parse_hook_string(hook_str, default_name=None):
    """Parses 'name:key=val,key2=val2' into a dictionary for recipes and pipelines.
    Safely ignores delimiters (:,=) when they are wrapped in double quotes.
    """

    # Split on the FIRST colon that is NOT inside quotes
    colon_parts = re.split(r':(?=(?:[^"]*"[^"]*")*[^"]*$)', hook_str, maxsplit=1)

    if len(colon_parts) > 1:
        name = colon_parts[0]
        rest = colon_parts[1]
        # Split on commas NOT inside quotes
        parts = re.split(r',(?=(?:[^"]*"[^"]*")*[^"]*$)', rest)
    else:
        name = hook_str
        parts = []

    name = name if name else default_name

    args = {}
    for part in parts:
        part = part.strip()
        if not part:
            continue

        # Split on the FIRST equals sign NOT inside quotes
        eq_parts = re.split(r'=(?=(?:[^"]*"[^"]*")*[^"]*$)', part, maxsplit=1)

        if len(eq_parts) > 1:
            k = eq_parts[0].strip()
            v = eq_parts[1].strip()

            # Strip surrounding quotes so the hook gets a clean string
            if len(v) >= 2 and v.startswith('"') and v.endswith('"'):
                v = v[1:-1]
            elif len(v) >= 2 and v.startswith("'") and v.endswith("'"):
                v = v[1:-1]

            if v.lower() in ["true", "yes"]:
                v = True
            elif v.lower() in ["false", "no"]:
                v = False
            else:
                try:
                    v = float(v) if "." in v else int(v)
                except ValueError:
                    pass
            args[k] = v
        else:
            args[part] = True

    hook = {"name": name}
    if args:
        hook["args"] = args
    return hook


def parse_source_string(source_str: str, default_hooks: Optional[List] = None) -> Dict:
    """Parses a source string into a Fetchez module dictionary.

    Supports local file auto-detection and chaining hooks via '+'.
    Safely ignores '+' delimiters when they are wrapped in double quotes.
    """

    # Split on '+' that are NOT inside quotes
    parts = re.split(r'\+(?=(?:[^"]*"[^"]*")*[^"]*$)', source_str)
    mod_part = parts[0]
    hook_parts = parts[1:]

    # Parse the hook strng
    mod_parsed = parse_hook_string(mod_part)
    mod_name = mod_parsed["name"]
    args = mod_parsed.get("args", {})

    # Auto-detect local files and directories
    mod_path = Path(mod_name)
    if mod_path.exists():
        if mod_path.is_file():
            args["paths"] = str(mod_path.resolve())
            mod_name = "file"
        elif mod_path.is_dir():
            args["path"] = str(mod_path.resolve())
            mod_name = "local_fs"

    mod_dict = {"module": mod_name, "hooks": default_hooks or []}
    if args:
        mod_dict["args"] = args

    # Parse and append chained hooks
    for h_str in hook_parts:
        mod_dict["hooks"].append(parse_hook_string(h_str))

    logger.debug(
        f"Parsed source string as: `{mod_name}` using hooks: {[x['name'] for x in mod_dict['hooks']]}"
    )  # {mod_dict['hooks']}")
    return mod_dict


def compile_sources(sources):

    import yaml
    from fetchez.registry import BundleRegistry

    BundleRegistry.load_all()

    compiled_modules = []
    for src in sources:
        if str(src) in BundleRegistry.get_registry().keys():
            partial_recipe = BundleRegistry.get_yaml(str(src))
            if "modules" in partial_recipe:
                compiled_modules.extend(partial_recipe["modules"])
                logger.debug(
                    f"Imported {len(partial_recipe['modules'])} modules from {src}"
                )
        elif str(src).lower().endswith((".yaml", ".yml")) and Path(src).exists():
            try:
                with open(src, "r") as f:
                    partial_recipe = yaml.safe_load(f)
                    modules = partial_recipe.get("modules")
                    if not modules:
                        modules = partial_recipe.get("config").get("modules")
                    if modules:
                        compiled_modules.extend(modules)
                        logger.debug(
                            f"Imported {len(partial_recipe['modules'])} modules from {src}"
                        )
            except Exception as e:
                logger.debug(f"Failed to read modules from {src}: {e}")
                continue
        elif src == "-":
            continue  # TODO: add stdin support
        else:
            compiled_modules.append(parse_source_string(src))

    return compiled_modules


def truncate_string(input_string: str, padding: int = 0):
    width, _ = shutil.get_terminal_size()
    width -= padding

    # Slice the string to fit exactly one line (minus 3 for the ellipsis)
    if len(input_string) > width:
        truncated_string = input_string[: width - 3] + "..."
    else:
        truncated_string = input_string
    return truncated_string


def parse_hook_string_(h_str):
    """Helper to parse 'hook:arg=val' strings."""

    if ":" in h_str:
        name, rest = h_str.split(":", 1)
        parts = rest.split(",")
    else:
        name = h_str
        parts = []

    kwargs = {}
    for p in parts:
        if "=" in p:
            k, v = p.split("=", 1)
            if v.lower() == "true":
                v = True
            elif v.lower() == "false":
                v = False
            else:
                try:
                    if "." in v:
                        v = float(v)
                    else:
                        v = int(v)
                except Exception as e:
                    logger.warning(f"Unable to parse hook string: {h_str}: {e}")
            kwargs[k] = v
        else:
            kwargs[p] = True
    return name, kwargs


def range_pairs(lst):
    return [(lst[i], lst[i + 1]) for i in range(len(lst) - 1)]


# TODO: Update this function to return a string instead of printing!
def get_class_arguments(TargetCls, want_inherited=True):
    """Inspect a class for arguments and print them out."""

    all_params = {}
    for cls in TargetCls.__mro__:
        if cls is object:
            continue

        if hasattr(cls, "__init__"):
            try:
                sig = inspect.signature(cls.__init__)
                for name, param in sig.parameters.items():
                    if name == "self" or param.kind in (
                        inspect.Parameter.VAR_POSITIONAL,
                        inspect.Parameter.VAR_KEYWORD,
                    ):
                        continue

                    if name not in all_params:
                        all_params[name] = {"param": param, "origin": cls}
            except ValueError:
                pass

    args_dict = {}
    if all_params:
        arg_help = getattr(TargetCls, "_cli_arg_help", {})
        for name, data in all_params.items():
            param = data["param"]
            origin_cls = data["origin"]
            origin_help = getattr(origin_cls, "_cli_arg_help", {})

            if param.default is inspect.Parameter.empty:
                default_str = colorize("(required)", RED)
            else:
                # default_str = f"(default: {param.default or 'None'})"
                default_str = param.default  # or None  # or 'None'}"

            type_str = ""
            if param.annotation is not inspect.Parameter.empty:
                type_name = getattr(param.annotation, "__name__", str(param.annotation))
                type_str = f"[{type_name}] "

            inherit_str = ""
            if origin_cls is not TargetCls:
                inherit_str = colorize(f" [from {origin_cls.__name__}]", CYAN)
                desc_str = f" - {origin_help[name]}" if name in origin_help else ""
            else:
                desc_str = f" - {arg_help[name]}" if name in arg_help else ""

            args_dict[name] = {
                "type": type_str,
                "default": default_str,
                "inherit": inherit_str,
                "desc": desc_str,
            }

    return args_dict


def _get_class_arguments(TargetClass):
    sig = inspect.signature(TargetClass.__init__)
    args_dict = {}
    for param_name, param in sig.parameters.items():
        if param_name in ["self", "kwargs", "args"]:
            continue

        default = (
            param.default
            if param.default is not inspect.Parameter.empty
            else "REQUIRED"
        )
        args_dict[param_name] = default

    return args_dict

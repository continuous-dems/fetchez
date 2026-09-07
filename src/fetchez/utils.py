#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
fetchez.utils
~~~~~~~~~~~~~~~~

Utility functions for colorized output, string manipulation,
and basic user interaction. Based on cudem.utils

:copyright: (c) 2012 - 2026 CIRES Coastal DEM Team
:license: MIT, see LICENSE for more details.
"""

import os
import sys
import datetime
import getpass
import logging
import zipfile
import shutil
import tempfile
from tqdm.auto import tqdm
import re
import inspect
import click
from pathlib import Path
from typing import Optional, Dict, Any, List

logger = logging.getLogger(__name__)

# =============================================================================
# ANSI Color Codes
# =============================================================================
BLACK = "\033[30m"
RED = "\033[31m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
BLUE = "\033[34m"
MAGENTA = "\033[35m"
CYAN = "\033[36m"
WHITE = "\033[37m"
RESET = "\033[0m"

BOLD = "\033[1m"
ITALIC = "\033[3m"
UNDERLINE = "\033[4m"
REVERSE = "\033[7m"

# ANSI Background Color Codes based on ETOPO soft palette
OCEAN = "\033[48;2;43;76;126m"  # Deep Ocean
MID = "\033[48;2;84;130;180m"  # Mid Ocean
LOW = "\033[48;2;133;181;141m"  # Lowland
FOOT = "\033[48;2;181;193;142m"  # Foothills
HIGH = "\033[48;2;212;190;157m"  # Highlands
ICE = "\033[48;2;244;247;250m"  # Ice
RST = "\033[0m"  # Reset


# =============================================================================
# Terminal Printing Helpers
# =============================================================================
def colorize(text: str, color: str) -> str:
    """Wrap text in ANSI color codes."""

    return f"{color}{text}{RESET}"


class TqdmLoggingHandler(logging.Handler):
    """A logging handler that outputs to tqdm.write() to avoid
    interfering with tqdm progress bars.
    """

    def __init__(self, level=logging.NOTSET):
        super().__init__(level)

    def emit(self, record):
        try:
            msg = self.format(record)
            tqdm.write(msg, file=sys.stderr)
            self.flush()
        except Exception:
            self.handleError(record)


def _cli_logo(name="fetchez", desc="", version=""):
    """Prints a colored ANSI block representation of the Fetchez logo."""

    # logo = f"""
    # {LOW}  {RST}{MID}  {RST}{FOOT}  {RST}{HIGH}  {RST}{MID}  {RST}
    # {OCEAN}  {RST}{LOW}  {RST}{HIGH}  {RST}{MID}  {RST}{FOOT}  {RST}   {colorize(name, MAGENTA)} {version}
    # {MID}  {RST}{OCEAN}  {RST}{MID}  {RST}{ICE}  {RST}{ICE}  {RST}   {colorize(desc, ITALIC)}
    # """
    logo = f"""
    {LOW}  {RST}{MID}  {RST}{FOOT}  {RST}  {colorize(name, MAGENTA)} {version}
    {OCEAN}  {RST}{ICE}  {RST}{HIGH}  {RST}  {colorize(desc, ITALIC)}
    """

    return logo


class FetchezMainGroup(click.Group):
    """Custom group to categorize the main CLI commands."""

    def __init__(self, fetchez_commands: Optional[List[str]] = None, **kwargs):
        super().__init__(**kwargs)

        self.fetchez_commands = fetchez_commands or []

    def format_usage(self, ctx, formatter):
        usage_pieces = self.collect_usage_pieces(ctx)
        formatter.write_usage(
            ctx.command_path,
            " ".join(usage_pieces),
            prefix=f"{colorize(colorize('Usage: ', GREEN), BOLD)}",
        )

    def format_options(self, ctx, formatter):
        opts = []
        for param in self.get_params(ctx):
            rv = param.get_help_record(ctx)
            if rv is not None:
                rv = (f"{colorize(colorize(rv[0], CYAN), BOLD):<30}", rv[1])
                opts.append(rv)

        if opts:
            with formatter.section(f"{colorize(colorize('Options', GREEN), BOLD)}"):
                formatter.write_dl(opts)

        self.format_commands(ctx, formatter)

    def format_commands(self, ctx, formatter):
        commands = []
        for subcommand in self.list_commands(ctx):
            cmd = self.get_command(ctx, subcommand)
            if cmd is None or cmd.hidden:
                continue
            commands.append((subcommand, cmd))

        if not commands:
            return

        if isinstance(self.fetchez_commands, dict):
            categories = {
                f"{colorize(colorize(k, GREEN), BOLD)}": v
                for k, v in self.fetchez_commands.items()
            }
        else:
            categories = {
                f"{colorize(colorize('Commands', GREEN), BOLD)}": self.fetchez_commands,
            }

        for cat_name, cmd_names in categories.items():
            with formatter.section(cat_name):
                cat_cmds = [
                    (
                        f"{colorize(colorize(name, CYAN), BOLD):<30}",
                        cmd.get_short_help_str(),  # limit=80
                    )
                    for name, cmd in commands
                    if name in cmd_names
                ]
                formatter.write_dl(cat_cmds)


class FetchezMainCommand(click.Command):
    """Custom command to colorize the main CLI commands."""

    # def __init__(self, **kwargs):
    #     super().__init__(**kwargs)

    def format_usage(self, ctx, formatter):
        usage_pieces = self.collect_usage_pieces(ctx)
        formatter.write_usage(
            ctx.command_path,
            " ".join(usage_pieces),
            prefix=f"{colorize(colorize('Usage: ', GREEN), BOLD)}",
        )

    def format_options(self, ctx, formatter):
        opts = []
        for param in self.get_params(ctx):
            rv = param.get_help_record(ctx)
            if rv is not None:
                rv = (f"{colorize(colorize(rv[0], CYAN), BOLD)}", rv[1])
                opts.append(rv)

        if opts:
            with formatter.section(f"{colorize(colorize('Options', GREEN), BOLD)}"):
                formatter.write_dl(opts)


# =============================================================================
# Data, Type and File Helpers
# =============================================================================
def this_date():
    """Get current date."""

    return datetime.datetime.now().strftime("%Y%m%d%H%M%S")


def today_str() -> str:
    # "YYYY-MM-DD"
    return datetime.datetime.now().strftime("%Y-%m-%d")


def get_username() -> str:
    username = ""
    while not username:
        username = input("username: ")
    return username.strip()


def get_password() -> str:
    password = ""
    while not password:
        password = getpass.getpass("password: ")
    return password.strip()


def int_or(val: Any, or_val: Optional[int] = None) -> Optional[int]:
    """Return val if val is an integer, else return or_val"""

    try:
        int_val = float_or(val)
        if int_val:
            return int(int_val)
        return or_val
    except Exception:
        return or_val


def float_or(val: Any, or_val: Optional[float] = None) -> Optional[float]:
    """Return val if val is a float, else return or_val"""

    try:
        return float(val)
    except Exception:
        return or_val


def str_or(
    instr: Any, or_val: Optional[str] = None, replace_quote: bool = True
) -> Optional[str]:
    """Return val if val is a string, else return or_val"""

    if instr is None:
        return or_val
    try:
        s = str(instr)
        return s.replace('"', "") if replace_quote else s
    except Exception:
        return or_val


def str2bool(v: Any) -> Optional[bool]:
    """Convert a string (or other type) to a boolean.

    Accepts:
      True:  'yes', 'true', 't', 'y', '1', 1, True
      False: 'no', 'false', 'f', 'n', '0', 0, False, None

    Args:
        v (str, int, bool): The value to convert.

    Returns:
        bool: The boolean representation of v.
    """

    if v is None:
        return None

    if isinstance(v, bool):
        return v

    if isinstance(v, (int, float)):
        return bool(v)

    v_str = str(v).lower().strip()

    if v_str in ("yes", "true", "t", "y", "1"):
        return True
    elif v_str in ("no", "false", "f", "n", "0"):
        return False
    else:
        return None


def str_truncate_middle(s: Optional[str], n: Optional[int] = 80) -> str:
    """Truncate the middle of the input string, replace with `...`"""

    s = str_or(s, "")
    n = int_or(n, 80)
    if s and n:
        if len(s) <= n:
            return s
        n_2 = n // 2 - 2
        return f"{s[:n_2]}...{s[-n_2:]}"
    return str(s)


def format_dataset_id(dataset_id: Optional[str]) -> str:
    """Extracts Context + Basename for logging."""

    from urllib.parse import urlparse

    dataset_id = str_or(dataset_id)
    if dataset_id:
        if dataset_id.startswith(("http://", "https://", "ftp://", "s3://")):
            parsed = urlparse(dataset_id)
            # context = parsed.netloc.split('.')[0]
            context = parsed.netloc
            basename = Path(parsed.path).name
        else:
            basename = Path(dataset_id).name
            context = Path(dataset_id).parent.name

        if not context:
            return basename

        return f"[{colorize(context, MAGENTA)}] {colorize(basename, BLUE)}"

    else:
        return str(dataset_id)


def fn_url_p(fn: str) -> bool:
    """Check if fn is a URL."""

    url_sw = ["http://", "https://", "ftp://", "ftps://", "/vsicurl"]
    if str_or(fn):
        try:
            for u in url_sw:
                if fn.startswith(u):
                    return True
        except Exception as e:
            logger.debug(f"Could not parse url {fn}: {e}")
            return False
    return False


def inc2str(inc: float) -> str:
    """Convert a WGS84 geographic increment to a string identifier."""

    import fractions

    return str(fractions.Fraction(str(inc * 3600)).limit_denominator(10)).replace(
        "/", ""
    )


def str2inc(inc_str: Optional[str]) -> Optional[float]:
    """Convert a GMT-style inc_str (e.g. 6s) to geographic units.

    c/s - arc-seconds
    m - arc-minutes
    t - meters
    """

    if inc_str is None or str(inc_str).lower() == "none" or len(str(inc_str)) == 0:
        return None

    inc_str = str_or(inc_str)
    if not inc_str:
        return None

    units = inc_str[-1]
    if float_or(units):
        return float_or(inc_str)

    inc_val = float_or(inc_str[:-1])
    if not inc_val:
        return None

    try:
        if units:
            if units == "c" or units == "s":
                return inc_val / 3600.0
            elif units == "m":
                return inc_val / 360.0
            elif units == "t":
                return inc_val / 111320.0  # Approx meters at equator
            else:
                logger.warning(
                    f"Unknown unit string: {units}, returning raw parsed value."
                )
                return float_or(inc_val)
        else:
            return float_or(inc_str)
    except ValueError as e:
        logger.error(f"Could not parse increment {inc_str}: {e}")
        return None


def remove_glob2(*args: str) -> int:
    """Glob paths and recursively delete matching files and directories."""

    for glob_pattern in args:
        try:
            # Match top-level paths based on the provided glob pattern
            # Uses Path(".") as the base directory anchor for the pattern
            if Path(glob_pattern).is_absolute():
                Path(glob_pattern).unlink(missing_ok=True)
            else:
                for path in Path(".").glob(glob_pattern):
                    if not path.exists():
                        continue
                    if path.is_dir() and not path.is_symlink():
                        shutil.rmtree(path)
                    else:
                        path.unlink(missing_ok=True)
        except Exception as e:
            logger.error(f"Could not remove path with glob pattern {glob_pattern}: {e}")
            return -1
    return 0


remove_glob = remove_glob2


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


def make_temp_fn(basename: str, temp_dir: Optional[str] = None) -> str:
    """Generate a temporary filename."""

    basename_path = Path(basename)
    prefix = basename_path.stem
    suffix = basename_path.suffix
    fd, path = tempfile.mkstemp(suffix=suffix, prefix=f"{prefix}_", dir=temp_dir)
    os.close(fd)
    return path


def x360(x: float) -> float:
    if x == 0:
        return -180
    elif x == 360:
        return 180
    else:
        return ((x + 180) % 360) - 180


# =============================================================================
# Factory Module parsing (from cudem)
# =============================================================================
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
        if str(src).lower().endswith((".yaml", ".yml")) and Path(src).exists():
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
            parsed = parse_source_string(src)
            name = parsed.get("module")
            if name in BundleRegistry.get_registry():
                parsed["bundle"] = parsed.pop("module")
            compiled_modules.append(parsed)

    return compiled_modules


def group_registry_by_key(registry, key="category"):
    grouped_hooks = {}
    if isinstance(registry, dict):
        registry_list = registry.items()
    elif isinstance(registry, list):
        registry_list = registry
    else:
        registry_list = [registry]

    for name, meta in registry_list:
        if name.split(".")[-1] in meta.get("aliases", []):
            continue
        cat = meta.get(key, "uncategorized").split(".")[0].title()
        if "fetchez_user" in cat.lower():
            cat = "User"

        grouped_hooks.setdefault(cat, []).append((name, meta))
    return grouped_hooks


def print_grouped_registry(grouped_hooks, registry_type="Modules", key="Provider"):
    import click

    click.secho(f"\n📜 Available {registry_type} by {key}:", fg="cyan", bold=True)
    click.echo("=" * 60)

    for cat in sorted(grouped_hooks.keys()):
        click.secho(f"\n[ {cat} ]", fg="yellow", bold=True)
        for name, meta in sorted(
            grouped_hooks[cat], key=lambda x: x[1].get("category", x[0])
        ):
            category = meta.get(
                "category", meta.get("Category", "Uncategorized")
            ).title()
            desc = (
                meta.get("desc", meta.get("description", "No description provided."))
                .strip()
                .split("\n")[0]
            )

            name_padded = f"{name:<26}"
            category_padded = f"[{category:^18}]"

            truncated_desc = truncate_string(
                desc, len(name_padded) + len(category_padded) + 7
            )
            click.echo(
                f"  {click.style(name_padded, bold=True, fg='green')} {click.style(category_padded, fg='blue')} : {truncated_desc}"
            )


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


# =============================================================================
# Archives, etc.
# =============================================================================
def p_unzip(src_fn: str, ext: list, outdir: str = ".", verbose: bool = False) -> list:
    """Unzip specific extensions from a zip file, optionally flattening directory structures.

    Args:
        src_fn: Path to the source zip file.
        ext: List of extensions to extract (e.g., ['shp', 'shx', 'dbf']).
        outdir: Directory to extract files into.
        verbose: Print debug info.

    Returns:
        List of paths to the extracted files.
    """
    if not Path(outdir).exists():
        Path(outdir).mkdir(parents=True, exist_ok=True)

    extracted_files = []

    try:
        with zipfile.ZipFile(src_fn, "r") as z:
            want_exts = [
                e.lower() if e.startswith(".") else f".{e.lower()}" for e in ext
            ]

            for file_info in z.infolist():
                if file_info.is_dir():
                    continue

                file_path = Path(file_info.filename)
                f_ext = file_path.suffix
                if f_ext.lower() in want_exts:
                    filename = file_path.name
                    target_path = Path(outdir) / filename

                    if verbose:
                        logger.info(f"Extracting {filename}...")

                    with z.open(file_info) as source, open(target_path, "wb") as target:
                        shutil.copyfileobj(source, target)

                    extracted_files.append(str(target_path))

    except zipfile.BadZipFile:
        logger.error(f"Bad Zip File: {src_fn}")
    except Exception as e:
        logger.error(f"Unzip error {src_fn}: {e}")

    return extracted_files


def p_f_unzip(src_file, fns=None, outdir="./", tmp_fn=False) -> List[str]:
    """Unzip specific files from src_file based on matches in `fns`."""

    if fns is None:
        fns = []

    extracted_paths = []
    ext = Path(src_file).suffix.lower()
    outdir = Path(outdir)

    if ext == ".zip":
        with zipfile.ZipFile(src_file, "r") as z:
            namelist = z.namelist()
            for pattern in fns:
                for member in namelist:
                    # Match pattern in the base filename
                    if pattern in Path(member).name:
                        if member.endswith("/"):  # Skip directories
                            continue

                        dest_fn = outdir / member.replace("\\", "/")
                        dest_fn.parent.mkdir(parents=True, exist_ok=True)
                        if tmp_fn:
                            dest_fn = make_temp_fn(member, temp_dir=outdir)

                        if dest_fn.exists() and not tmp_fn:
                            logger.debug(f"Skipping extraction, file exists: {dest_fn}")
                            extracted_paths.append(str(dest_fn))
                            continue

                        # Extract and write the file
                        with open(dest_fn, "wb") as f:
                            f.write(z.read(member))
                        extracted_paths.append(str(dest_fn))
                        logger.debug(f"Extracted: {member} to {dest_fn}")
    else:
        # Fallback if the file isn't a zip
        for pattern in fns:
            if pattern == Path(src_file).parent:
                extracted_paths.append(src_file)
                break
    return extracted_paths


# =============================================================================
# Hooks
# =============================================================================
def merge_hooks(global_hooks, local_hooks):
    """Merge global and local hooks.

    Order: Globals first, then Locals.

    Duplicate removal has been removed to allow nested sub-pipelines,
    but we log a debug warning if exact duplicates cross the global/local boundary.
    """

    import logging

    logger = logging.getLogger(__name__)

    merged = list(global_hooks)

    for h in local_hooks:
        if h in global_hooks:
            logger.debug(
                f"Duplicate hook '{h.name}' detected in both global and local scopes. "
                "Preserving both to support sequential sub-pipelines."
            )
        merged.append(h)

    return merged


# Depreciated due to removing duplicates!
def _merge_hooks(global_hooks, local_hooks):
    """Merge global and local hooks, removing exact duplicates.

    Order: Globals first, then Locals.
    """

    merged = []
    for h in global_hooks:
        if h not in merged:
            merged.append(h)

    for h in local_hooks:
        if h not in merged:
            merged.append(h)

    return merged


def _log_hook_history(entries, hook):
    """Append a history record to every entry in the list."""

    if not entries:
        return

    history_record = {
        "hook": hook.name,
        "stage": hook.stage,
        "timestamp": datetime.datetime.now().isoformat(),
    }

    for _mod, entry in entries:
        if "history" not in entry:
            entry["history"] = []

        if entry["history"]:
            last = entry["history"][-1]
            if (
                last["hook"] == history_record["hook"]
                and last["stage"] == history_record["stage"]
            ):
                continue

        entry["history"].append(history_record.copy())


# =============================================================================
# Functions
# =============================================================================
def _linspace(start, stop, num=50):
    if num < 2:
        return [float(start)] if num == 1 else []

    # Calculate step size
    step = (stop - start) / (num - 1)

    # Generate the list
    return [start + i * step for i in range(num)]

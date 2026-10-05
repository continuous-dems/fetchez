#!/usr/bin/env python

"""
fetchez.cli
~~~~~~~~~~~~~

This module contains the CLI for the Fetchez library.

:copyright: (c) 2010-2026 Regents of the University of Colorado
:license: MIT, see LICENSE for more details.
"""

import argparse
import inspect
import logging
import signal
import sys
from pathlib import Path
from typing import Any

from . import __version__, core, spatial, utils
from .recipe import Recipe
from .registry import HookRegistry, ModuleRegistry, PresetRegistry, RecipeRegistry

logger = logging.getLogger(__name__)


# =============================================================================
# CLI Decorator and Decorations and logging
# =============================================================================
def cli_opts(help_text: str | None = None, **arg_help):
    """Decorator to attach CLI help text to FetchModule classes.

    Args:
        help_text: The description for the module's sub-command.
        **arg_help: Key-value pairs matching __init__ arguments to help strings.
    """

    def decorator(cls):
        cls._cli_help_text = help_text
        cls._cli_arg_help = arg_help
        return cls

    return decorator


# This is duplicated in fetchez.recipe
# We should move this to utils
def setup_logging(quiet=False, verbose=False):
    if quiet:
        log_level = logging.WARNING
    elif verbose:
        log_level = logging.DEBUG
    else:
        log_level = logging.INFO

    logger = logging.getLogger("fetchez")
    logger.setLevel(log_level)

    logger.propagate = False

    if logger.hasHandlers():
        logger.handlers.clear()

    handler = utils.TqdmLoggingHandler()

    # formatter = logging.Formatter("[ %(levelname)s ] %(name)s: %(message)s")
    formatter = logging.Formatter("[ %(levelname)s ] %(module)s: %(message)s")
    handler.setFormatter(formatter)

    logger.addHandler(handler)


# =============================================================================
# Argparse helpers
#
# Mostly based on cudem.factory
# =============================================================================
def parse_fmod_argparse(arg_str):
    """Parse 'module:key=val,key2=val2' strings into argparse-ready flags.

    Input:  'srtm_plus:year=2020,verbose'
    Output: (None, 'srtm_plus', ['--year=2020', '--verbose'])
    """

    if ":" in arg_str:
        mod_name, rest = arg_str.split(":", 1)
        parts = rest.split(",")
    else:
        mod_name = arg_str
        parts = []

    args = []

    for p in parts:
        if not p.strip():
            continue

        # Convert 'key=val' to '--key=val' for argparse
        if "=" in p:
            k, v = p.split("=", 1)
            args.append(f"--{k}={v}")
        else:
            # Handle boolean flags passed without value (e.g. ,verbose)
            args.append(f"--{p}")

    return None, mod_name, args


def _populate_subparser(subparser, module_cls, global_args=None):
    """Introspect module __init__ to populate subparser arguments."""

    if not module_cls:
        return

    global_args = global_args or ["self", "kwargs", "params"]
    sig = inspect.signature(module_cls.__init__)

    # Get help text from decorator if available
    arg_help = getattr(module_cls, "_cli_arg_help", {})

    for name, param in sig.parameters.items():
        # Skip base FetchModule arguments that are handled globally
        if name in [
            "self",
            "kwargs",
            "src_region",
            "callback",
            "outdir",
            "name",
            "params",
        ]:
            continue

        # Determine help string
        help_str = arg_help.get(name, f"Set {name} parameter")

        ## Determine type and default
        default = param.default
        if default is inspect.Parameter.empty:
            default = None

        # Handle Boolean Flags
        if param.annotation is bool or isinstance(default, bool):
            action = "store_true" if not default else "store_false"
            subparser.add_argument(f"--{name}", action=action, help=help_str)
        else:
            type_fn = None
            if param.annotation is int:
                type_fn = int
            elif param.annotation is float:
                type_fn = float

            subparser.add_argument(
                f"--{name}",
                default=default,
                type=type_fn,
                help=f"{help_str} (default: {default})",
            )


# =============================================================================
# Registry & Help Helpers
# =============================================================================
def get_module_cli_desc(m: dict) -> str:
    """Generates a formatted, categorized list of modules using Registry metadata."""

    CATEGORY_ORDER = [
        "Topography",
        "Bathymetry",
        "Oceanography",
        "Imagery",
        "Reference",
        "Generic",
    ]
    grouped_modules: dict[Any, Any] = {}

    for key, val in m.items():
        if key in val.get("aliases", []):
            continue

        cat = val.get("category", "Generic")
        if cat not in grouped_modules:
            grouped_modules[cat] = []

        desc = val.get("desc", f"Fetch data from {key}")
        agency = val.get("agency", "")

        grouped_modules[cat].append((key, desc, agency))

    rows = []
    existing_cats = [c for c in CATEGORY_ORDER if c in grouped_modules]
    remaining_cats = sorted([c for c in grouped_modules if c not in CATEGORY_ORDER])

    for cat in existing_cats + remaining_cats:
        rows.append(f"\n{utils.colorize(f'[ {cat} ]', utils.CYAN)}")

        for name, desc, agency in sorted(grouped_modules[cat], key=lambda x: x[0]):
            name_padded = f"{name:<18}"
            agency_str = f"[{agency}]" if agency else ""
            agency_padded = f"{agency_str:<12}"

            rows.append(
                f"  \033[1m{name_padded}\033[0m "
                f"{utils.colorize(agency_padded, utils.YELLOW)} : {desc}"
            )

    return "\n".join(rows)


class PrintModulesAction(argparse.Action):
    def __call__(self, parser, namespace, values, option_string=None):
        print(f"""
Supported fetchez modules (see {Path(sys.argv[0]).name} <module-name> --help for more info):
{get_module_cli_desc(ModuleRegistry.get_registry())}
""")
        sys.exit(0)


def print_module_info(mod_key):
    """Pretty-print module metadata."""

    meta = ModuleRegistry.get_info(mod_key)
    if not meta:
        logger.error(f"Module {mod_key} not found.")
        return

    print(f"\n{utils.CYAN}MODULE: {mod_key.upper()}{utils.RESET}")
    print(f"{'-' * 40}")
    print(f"  Description : {meta.get('desc', 'N/A')}")
    print(f"  Provider    : {meta.get('agency', 'Unknown')}")
    print(f"  Category    : {meta.get('category', 'Generic')}")
    print(f"  Coverage    : {meta.get('region', 'Unknown')}")
    print(f"  Resolution  : {meta.get('resolution', 'Unknown')}")
    print(f"  License     : {meta.get('license', 'Unknown')}")
    print(f"  Tags        : {', '.join(meta.get('tags', []))}")

    if "urls" in meta:
        print("\n  Links:")
        for k, v in meta["urls"].items():
            print(f"    {k:<10}: {v}")

    # --- INSPECT FOR ARGUMENTS ---
    ModuleCls = ModuleRegistry.get_class(mod_key)
    if ModuleCls:
        print_class_arguments(ModuleCls)

    print(f"{'-' * 40}\n")


def print_hook_info(hook_key):
    """Pretty-print hook metadata and its available arguments."""

    meta = HookRegistry.get_info(hook_key)
    if not meta:
        logger.error(f"Hook '{hook_key}' not found.")
        return

    print(f"\n🪝 {utils.CYAN}HOOK: {hook_key.upper()}{utils.RESET}")
    print(f"{'-' * 60}")
    print(f"  Description : {meta.get('desc', 'No description provided.')}")
    print(f"  Domain      : {meta.get('domain', 'Universal (Files)')}")
    print(f"  Requires    : {meta.get('requires', 'any')}")
    print(f"  Stage       : {meta.get('stage', 'Unknown')}")
    print(f"  Type        : {meta.get('category', 'Generic')}")
    print(f"  Origin      : {meta.get('mod', 'Unknown')}")

    # --- INSPECT FOR ARGUMENTS ---
    HookCls = HookRegistry.get_class(hook_key)
    if HookCls:
        print_class_arguments(HookCls)

    print(f"{'-' * 60}\n")


def print_class_arguments(TargetCls, want_inherited=True):
    """Inspect a class for arguments and print them out."""

    print(f"\n  {utils.colorize('Available Arguments:', utils.YELLOW)}")

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

    if all_params:
        arg_help = getattr(TargetCls, "_cli_arg_help", {})
        for name, data in all_params.items():
            param = data["param"]
            origin_cls = data["origin"]

            if param.default is inspect.Parameter.empty:
                default_str = utils.colorize("(required)", utils.RED)
            else:
                default_str = f"(default: {param.default})"

            type_str = ""
            if param.annotation is not inspect.Parameter.empty:
                type_name = getattr(param.annotation, "__name__", str(param.annotation))
                type_str = f"[{type_name}] "

            inherit_str = ""
            if origin_cls is not TargetCls:
                # Differentiate it visually, e.g., in cyan or dim text
                inherit_str = utils.colorize(
                    f" [from {origin_cls.__name__}]", utils.CYAN
                )

            desc_str = f" - {arg_help[name]}" if name in arg_help else ""

            print(
                f"    {utils.colorize(name, utils.BOLD):<15} {type_str}{default_str}{inherit_str}{desc_str}"
            )
    else:
        print("    (No specific arguments required)")


def parse_hook_arg(arg_str):
    """Parse a hook string into (name, kwargs).

    ** Depreciated - use `utils.parse_hook_string` **

    Syntax: 'name:key=val,key2=val2'
    Example: 'reproject:crs=EPSG:3857,verbose=true'
    """

    if ":" in arg_str:
        name, rest = arg_str.split(":", 1)
        parts = rest.split(",")
    else:
        name = arg_str
        parts = []

    kwargs = {}

    for p in parts:
        if not p.strip():
            continue

        if "=" in p:
            k, v = p.split("=", 1)

            if v.lower() == "true":
                kwargs[k] = True
            elif v.lower() == "false":
                kwargs[k] = False
            elif v.startswith("."):
                kwargs[k] = v
            else:
                try:
                    if "." in v:
                        kwargs[k] = float(v)
                    else:
                        kwargs[k] = int(v)
                except ValueError:
                    kwargs[k] = v
        else:
            # Boolean flag
            kwargs[p] = True

    return name, kwargs


def init_hooks(hook_list_strs):
    """Convert a list of strings ['pipe', 'unzip:force=true'] into initialized Hook objects."""

    active_instances = []
    if not hook_list_strs:
        return active_instances

    for h_str in hook_list_strs:
        parsed = utils.parse_hook_string(h_str)
        name = parsed["name"]
        kwargs = parsed.get("args", {})

        HookCls = HookRegistry.get_class(name)
        if HookCls:
            try:
                instance = HookCls(**kwargs)
                active_instances.append(instance)
            except Exception as e:
                logger.error(f'Failed to initialize hook "{name}": {e}')
        else:
            logger.warning(
                f'Hook "{name}" not found. Use --list-hooks to see available plugins.'
            )

    return active_instances


def init_presets():
    """Generate a default presets.yaml file."""

    import yaml

    from . import config

    config_dir = config.CONFIG_PATH
    config_file = Path(config_dir) / "presets.yaml"

    if config_file.exists():
        logger.warning(f"Config file already exists at: {config_file}")
        return

    config_dir.mkdir(parents=True, exist_ok=True)

    default_config = {
        "presets": {
            "audit-full": {
                "description": "Generate SHA256 hashes, enrichment, and a full JSON audit log.",
                "hooks": [
                    {"name": "checksum", "args": {"algo": "sha256"}},
                    {"name": "enrich"},
                    {"name": "audit", "args": {"file": "audit_full.json"}},
                ],
            },
            "clean-download": {
                "description": "Unzip files and remove the original archive.",
                "hooks": [{"name": "unzip", "args": {"remove": "true"}}],
            },
            "inf_only": {
                "target_module": "multibeam",
                "description": "multibeam Only: Fetch only inf files",
                "hooks": [
                    {
                        "name": "filename_filter",
                        "args": {"match": ".inf", "stage": "pre"},
                    },
                ],
            },
        },
    }

    try:
        with open(config_file, "w") as f:
            f.write("# Fetchez User Configuration & Presets\n")
            f.write("# Define your custom workflow macros here.\n\n")
            yaml.dump(default_config, f, sort_keys=False, default_flow_style=False)

        logger.info(f"Created default configuration at: {config_file}")
        logger.info("Edit this file to add your own workflow presets.")
    except Exception as e:
        logger.error(f"Could not create presets config: {e}")


# =============================================================================
# Command-line Interface(s) (CLI)
#
# `get_parser` here was extracted so we can auto-document the cli with Sphinx.
# =============================================================================
def get_parser():
    _usage = "%(prog)s [-R REGION] [OPTIONS] MODULE [MODULE-OPTS]..."

    parser = argparse.ArgumentParser(
        # description=f"{utils.CYAN}%(prog)s{utils.RESET} ({__version__}) :: Discover and Fetch remote geospatial data",
        description=utils._cli_logo(
            "fetchez", "Fetch geospatial data with ease.", __version__
        ),
        formatter_class=argparse.RawTextHelpFormatter,
        add_help=False,
        usage=_usage,
        epilog="""
Examples:
  fetchez -R -105/-104/39/40 srtm_plus
  fetchez -R loc:"Boulder, CO" copernicus --datatype=1
  fetchez -R loc:seattle -H4 charts --hook unzip --hook filename_filter:match=.000 --pipe-path
  fetchez --search-modules bathymetry

CUDEM home page: <http://cudem.colorado.edu>
        """,
    )

    sel_grp = parser.add_argument_group("Geospatial Selection")
    sel_grp.add_argument(
        "-R", "--region", "--aoi", action="append", help=spatial.region_help_msg()
    )
    sel_grp.add_argument(
        "-B",
        "--buffer",
        type=float,
        default=0,
        metavar="PCT",
        help="Buffer the input region by PCT percent.",
    )

    disc_grp = parser.add_argument_group("Discovery & Metadata")
    disc_grp.add_argument(
        "--list-modules",
        nargs=0,
        action=PrintModulesAction,
        help="List all available data modules.",
    )
    disc_grp.add_argument(
        "--list-hooks", action="store_true", help="List all available hooks."
    )
    disc_grp.add_argument(
        "--list-presets", action="store_true", help="List all available hook presets."
    )
    disc_grp.add_argument(
        "--list-recipes",
        action="store_true",
        help="List all curated recipes available in the registry.",
    )
    disc_grp.add_argument(
        "--search-modules",
        metavar="TERM",
        help="Search modules by tag, agency, or description.",
    )
    # disc_grp.add_argument(
    #     "--search-hooks",
    #     metavar="TERM",
    #     help="Search hook by keyword.",
    # )
    disc_grp.add_argument(
        "--module-info",
        metavar="MODULE",
        help="Show detailed metadata for a specific module.",
    )
    disc_grp.add_argument(
        "--hook-info",
        metavar="HOOK_NAME",
        type=str,
        help="Print detailed documentation and arguments for a specific hook.",
    )

    disc_grp.add_argument(
        "-h", "--help", action="store_true", help="Show this help message and exit."
    )
    disc_grp.add_argument(
        "--version", action="version", version=f"%(prog)s {__version__}"
    )

    exec_grp = parser.add_argument_group("Execution Control")
    exec_grp.add_argument(
        "-r",
        "--recipe",
        type=str,
        default=None,
        help="The YAML Recipe file to process or Keyword.",
    )
    exec_grp.add_argument(
        "--hook",
        action="append",
        help="Add a custom global hook (e.g. 'audit:file=log.txt').",
    )
    exec_grp.add_argument(
        "-O",
        "--outdir",
        default=None,
        metavar="DIR",
        help="Base output directory (default: current working directory).",
    )
    exec_grp.add_argument(
        "-H",
        "--threads",
        type=int,
        default=1,
        metavar="N",
        help="Number of parallel download threads (default: 1).",
    )
    exec_grp.add_argument(
        "-A",
        "--attempts",
        type=int,
        default=5,
        metavar="N",
        help="Number of retry attempts per file (default: 5).",
    )
    exec_grp.add_argument(
        "-q",
        "--quiet",
        action="store_true",
        help="Suppress progress bars and status messages.",
    )
    exec_grp.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable verbose (DEBUG) logging.",
    )

    preset_grp = parser.add_argument_group("Pipeline Shortcuts (Hook Presets)")
    preset_grp.add_argument(
        "-l",
        "--list",
        action="store_true",
        help="List discovered URLs to stdout (Pre-Hook).",
    )
    preset_grp.add_argument(
        "--init-presets",
        action="store_true",
        help="Generate a default ~/.fetchez/presets.yaml file.",
    )
    preset_grp.add_argument(
        "--inventory",
        metavar="FMT",
        nargs="?",
        const="json",
        help="Print manifest of files to be fetched (default: json). Prevents download.",
    )
    preset_grp.add_argument(
        "--pipe-path",
        action="store_true",
        help="Print absolute paths of downloaded files for piping (Post-Hook).",
    )
    preset_grp.add_argument(
        "--audit-log",
        metavar="FILE",
        help="Generate a full audit log with Checksums and Metadata.",
    )

    # User presets
    PresetRegistry.load_all()
    for name, defs in PresetRegistry.get_registry().items():
        if not defs.get("target_module"):
            flag_name = f"--{name}"
            help_text = defs.get("description", "Custom user preset.")
            preset_grp.add_argument(flag_name, action="store_true", help=help_text)

    # adv_grp = parser.add_argument_group("Advanced Configuration")

    return parser


def fetchez_cli():
    """Run fetchez from command-line using argparse."""

    try:
        signal.signal(signal.SIGPIPE, signal.SIG_DFL)
    except AttributeError:
        # Windows does not strictly support SIGPIPE in the same way
        pass

    _usage = "%(prog)s [-R REGION] [OPTIONS] MODULE [MODULE-OPTS]..."

    ModuleRegistry.load_all()
    HookRegistry.load_all()
    PresetRegistry.load_all()

    # user_presets = presets.get_global_presets()
    # user_mod_presets = config.load_user_config("presets").get("modules", {})

    parser = get_parser()

    # Pre-process Arguments to fix argparses handling of -R
    fixed_argv = spatial.fix_argparse_region(sys.argv[1:])
    global_args, remaining_argv = parser.parse_known_args(fixed_argv)

    # level = logging.WARNING if global_args.quiet else logging.INFO
    # I like sending logging to stderr, and anyway we want this with --pipe-path
    # logging.basicConfig(level=level, format='[ %(levelname)s ] %(name)s: %(message)s', stream=sys.stderr)
    setup_logging(
        quiet=global_args.quiet, verbose=getattr(global_args, "verbose", False)
    )

    if global_args.init_presets:
        init_presets()
        sys.exit(0)

    # --- MODULE INFO ---
    if global_args.module_info:
        print(
            utils._cli_logo("fetchez", "Fetch geospatial data with ease.", __version__)
        )
        print_module_info(global_args.module_info)
        sys.exit(0)

    if global_args.search_modules:
        print(
            utils._cli_logo("fetchez", "Fetch geospatial data with ease.", __version__)
        )
        results = ModuleRegistry.search_modules(global_args.search_modules)

        if not results:
            logger.warning(f'No modules found matching "{global_args.search_modules}"')
            sys.exit(0)

        print(
            f'\nSearch results for "{utils.colorize(global_args.search_modules, utils.CYAN)}":'
        )
        print("-" * 60)

        for mod_key in results:
            info = ModuleRegistry.get_info(mod_key)
            desc = info.get("desc", "No description")
            agency = info.get("agency", "")

            print(
                f"{utils.colorize(mod_key, utils.BOLD):<15} {utils.colorize(f'[{agency}]', utils.YELLOW):<10} {desc}"
            )

            tags = ", ".join(info.get("tags", [])[:5])  # limit to 5 tags
            if tags:
                print(f"    ↳ tags: {tags}")

        print("-" * 60)
        sys.exit(0)

    # --- HOOK INFO ---
    if global_args.hook_info:
        print(
            utils._cli_logo("fetchez", "Fetch geospatial data with ease.", __version__)
        )
        print_hook_info(global_args.hook_info)
        sys.exit(0)

    if hasattr(global_args, "list_hooks") and global_args.list_hooks:
        print(
            utils._cli_logo("fetchez", "Fetch geospatial data with ease.", __version__)
        )
        print("\nAvailable Hooks:")
        print("=" * 60)

        # Testing new list-hooks by domain and requirements
        # Group by domain using the parsed registry metadata
        # grouped_hooks = {}
        # for name, meta in HookRegistry.get_registry().items():
        #     if name in meta.get("aliases", []):
        #         continue

        #     # Default to universal if no domain is specified
        #     # domain = meta.get("domain", "Universal (Files)")
        #     domain = meta.get("category", "Universal (Files)")
        #     if domain not in grouped_hooks:
        #         grouped_hooks[domain] = []
        #     grouped_hooks[domain].append((name, meta))

        # # Sort domains (Universal first, then specialized)
        # domains = sorted(
        #     grouped_hooks.keys(), key=lambda x: (x != "Universal (Files)", x)
        # )

        # for domain in domains:
        #     print(f"\n{utils.CYAN}[ {domain.upper()} ]{utils.RESET}")

        #     for name, meta in sorted(grouped_hooks[domain], key=lambda x: x[0]):
        #         desc = meta.get("desc", "No description provided.")
        #         requires = meta.get("requires", "any")

        #         print(
        #             f"  {utils.colorize(name, utils.BOLD):<25} "
        #             f"{utils.colorize(f'Requires: {requires}', utils.YELLOW):<25} : {desc}"
        #         )

        # Group by category using the parsed registry metadata
        grouped_hooks = {}
        for name, meta in HookRegistry.get_registry().items():
            # Skip aliases so we don't print duplicate entries
            if name in meta.get("aliases", []):
                continue

            cat = meta.get("category", "uncategorized")
            if cat not in grouped_hooks:
                grouped_hooks[cat] = []
            grouped_hooks[cat].append((name, meta))

        # Define display order
        cat_order = [
            "pipeline",
            "metadata",
            "file-op",
            "stream-transform",
            "stream-filter",
            "sink",
            "uncategorized",
        ]
        existing_cats = [c for c in cat_order if c in grouped_hooks]
        remaining_cats = sorted([c for c in grouped_hooks if c not in cat_order])

        for cat in existing_cats + remaining_cats:
            # Format header: [ Metadata ]
            print(f"\n{utils.CYAN}[ {cat.title()} ]{utils.RESET}")

            for name, meta in sorted(grouped_hooks[cat], key=lambda x: x[0]):
                # Grab the cleaned metadata directly from the dictionary
                desc = meta.get("desc", "No description provided.")
                mod_path = meta.get("mod", "")

                # Determine the origin of the hook
                if mod_path:
                    origin = mod_path.split(".")[0].capitalize()
                else:
                    origin = "User Plugin"

                cat_stage = meta.get("stage", "file")
                if cat_stage == "pre":
                    cat_stage = "manifest"
                if cat_stage == "post":
                    cat_stage = "collection"
                # Print with origin tag in yellow
                print(
                    f"  {utils.colorize(name, utils.BOLD):<26} "
                    f"{utils.colorize(f'[{origin}]', utils.YELLOW):<13} : {desc}"
                )

        print()
        sys.exit(0)

    if getattr(global_args, "list_presets", False):
        registry = PresetRegistry.get_registry()

        print("\nAvailable Curated Presets:")
        print("=" * 60)
        count = 0
        for name, meta in sorted(registry.items()):
            print(f"  {name:<25} - {meta.get('description', 'Imported Preset')}")
            count += 1
        print("=" * 60)
        print(f"Total presets found: {count}\n")
        sys.exit(0)

    # --- Run/list a recipe.yaml ---
    if getattr(global_args, "list_recipes", False):
        RecipeRegistry.load_all()
        registry = RecipeRegistry.get_registry()

        print("\nAvailable Curated Recipes:")
        print("=" * 60)
        count = 0
        for name, meta in sorted(registry.items()):
            print(f"  {name:<25} - {meta['desc']}")
            count += 1
        print("=" * 60)
        print(f"Total recipes found: {count}\n")
        sys.exit(0)

    if getattr(global_args, "recipe", None):
        import yaml

        RecipeRegistry.load_all()
        target = global_args.recipe
        base_config = None

        if Path(target).exists():
            with open(target, "r", encoding="utf-8") as f:
                base_config = yaml.safe_load(f)
        else:
            recipe_meta = RecipeRegistry.get_recipe(target)
            if recipe_meta:
                base_config = recipe_meta["config"]
                logger.info(f"Loaded registered recipe: {target}")

        if not base_config:
            logger.error(f"Recipe '{target}' not found locally or in the registry.")
            sys.exit(1)

        if getattr(global_args, "region", None):
            base_config["region"] = global_args.region

        [r for r in Recipe.from_file(base_config).run()]
        sys.exit(0)

    # if hasattr(global_args, "recipe") and global_args.recipe:
    #     project_file = global_args.recipe
    #     if project_file.endswith(".yaml"):
    #         recipe = Recipe.from_file(project_file)
    #         recipe.run()
    #         sys.exit(0)

    # --- Init Global Hook Shortcuts ---
    global_hook_objs = []
    if hasattr(global_args, "hook") and global_args.hook:
        # global_hook_objs = init_hooks(global_args.hook)
        global_hook_objs.extend(init_hooks(global_args.hook))

    # --- Process Default Presets ---
    for preset_name, preset_def in PresetRegistry.get_registry().items():
        cli_arg_name = preset_name.replace("-", "_")
        if getattr(global_args, cli_arg_name, False):
            for hook_def in preset_def.get("hooks", []):
                h_name = hook_def.get("name")
                h_kwargs = hook_def.get("args", {})
                HookCls = HookRegistry.get_class(h_name)
                if HookCls:
                    global_hook_objs.append(HookCls(**h_kwargs))

    if global_args.list:
        from .hooks.dryrun import DryRun
        from .hooks.list_entries import ListEntries

        global_hook_objs.append(ListEntries())
        if not any(h.name == "dryrun" for h in global_hook_objs):
            global_hook_objs.append(DryRun())

    if global_args.inventory:
        from .hooks.dryrun import DryRun
        from .hooks.inventory import Inventory

        fmt = global_args.inventory
        global_hook_objs.append(Inventory(format=fmt))
        if not any(h.name == "dryrun" for h in global_hook_objs):
            global_hook_objs.append(DryRun())

    if global_args.pipe_path:
        from .hooks.pipe import PipeOutput

        global_hook_objs.append(PipeOutput())

    if global_args.audit_log:
        from .hooks.audit import Audit
        from .hooks.checksum import Checksum
        from .hooks.enrich import MetadataEnrich

        global_hook_objs.append(Checksum(algo="md5"))
        global_hook_objs.append(MetadataEnrich())
        global_hook_objs.append(Audit(file=global_args.audit_log))

    # --- Parse out modules/commands ---
    module_keys = {}
    for key, val in ModuleRegistry.get_registry().items():
        module_keys[key] = key
        for alias in val.get("aliases", []):
            module_keys[alias] = key

    commands = []
    current_cmd = None
    current_args = []
    for arg in remaining_argv:
        is_module = (arg in module_keys) or (arg.split(":")[0] in module_keys)

        is_url = False
        try:
            import urllib

            parsed = urllib.parse.urlparse(arg)
            if parsed.scheme in ["http", "https", "ftp"]:
                is_url = True
        except Exception:
            pass

        if is_module and not arg.startswith("-") and not is_url:
            if current_cmd:
                commands.append((current_cmd, current_args))

            if len(arg.split(":")) > 1:
                _, raw_name, current_args = parse_fmod_argparse(arg)
                current_cmd = module_keys.get(raw_name, raw_name)
            else:
                current_cmd = module_keys.get(arg, arg)
                current_args = []
        elif is_url:
            if current_cmd == "url_fetcher":
                if current_args and current_args[0].startswith("--url="):
                    commands.append((current_cmd, current_args))
                    current_cmd = "url_fetcher"
                    current_args = [f"--url={arg}"]
                else:
                    current_args.append(f"--url={arg}")
            else:
                if current_cmd:
                    commands.append((current_cmd, current_args))
                current_cmd = "url_fetcher"
                current_args = [f"--url={arg}"]
        else:
            if (
                current_cmd
                and current_cmd not in ["file", "url_fetcher"]
                or current_cmd == "file"
                and arg.startswith("-")
            ):
                current_args.append(arg)
            elif Path(arg).is_file():
                if current_cmd == "file":
                    if current_args and current_args[0].startswith("--paths="):
                        current_args[0] += f",{arg}"
                    else:
                        current_args.append(f"--paths={arg}")
                else:
                    current_cmd = "file"
                    current_args = [f"--paths={arg}"]

    if current_cmd:
        commands.append((current_cmd, current_args))

    if global_args.help:
        if not commands:
            parser.print_help()
            sys.exit(0)
        else:
            commands[0][1].append("--help")

    if not commands:
        parser.print_help()
        logger.error("You must select at least one module")
        sys.exit(0)

    if not global_args.region:
        these_regions = [(-180, 180, -90, 90)]
    else:
        these_regions = spatial.parse_region(global_args.region)

    if global_args.buffer > 0:
        these_regions = [
            spatial.buffer_region(r, global_args.buffer) for r in these_regions
        ]

    # --- Parse Module args ---
    usable_modules = []
    for mod_key, mod_argv in commands:
        # LOAD MODULE HERE
        mod_cls = ModuleRegistry.get_class(mod_key)
        if mod_cls is None:
            logger.error(f"Could not load module: {mod_key}")
            continue

        mod_parser = argparse.ArgumentParser(
            prog=f"fetchez [OPTIONS] {mod_key}",
            description=mod_cls.__doc__,
            add_help=True,
            formatter_class=argparse.RawTextHelpFormatter,
        )
        mod_parser.add_argument(
            "--mod-hook", action="append", help=f"Add a hook for {mod_key} only."
        )
        mod_parser.add_argument(
            "--weight",
            type=float,
            default=1,
            metavar="W",
            help=f"Set the weight for {mod_key} data (default: 1).",
        )
        mod_parser.add_argument(
            "--outdir",
            type=str,
            default=None,
            metavar="DIR",
            help=f"Override output directory for {mod_key}.",
        )

        active_presets = getattr(mod_cls, "presets", {}).copy()
        for preset_name, preset_def in PresetRegistry.get_registry().items():
            # Only attach if this preset is explicitly targeted at this module
            if preset_def.get("target_module") == mod_key:
                active_presets.update({preset_name: preset_def})

        if active_presets:
            mod_preset_grp = mod_parser.add_argument_group(f"{mod_key} Presets")
            for preset_name, preset_def in active_presets.items():
                help_text = preset_def.get("help", f"Apply {preset_name} preset.")
                flag = f"--{preset_name.replace('_', '-')}"
                mod_preset_grp.add_argument(flag, action="store_true", help=help_text)

        _populate_subparser(mod_parser, mod_cls)
        mod_args_ns = mod_parser.parse_args(mod_argv)
        mod_kwargs = vars(mod_args_ns)

        if mod_kwargs.get("outdir") is None:
            mod_kwargs["outdir"] = global_args.outdir

        if mod_kwargs.get("mod_hook"):
            mod_kwargs["hook"] = init_hooks(mod_kwargs["mod_hook"])
        else:
            mod_kwargs["hook"] = []

        del mod_kwargs["mod_hook"]

        for pname, pdef in active_presets.items():
            arg_attr = pname.replace("-", "_")
            if getattr(mod_args_ns, arg_attr, False):
                for hook_def in pdef.get("hooks", []):
                    h_name = hook_def.get("name")
                    h_kwargs = hook_def.get("args", {})
                    HookCls = HookRegistry.get_class(h_name)
                    if HookCls:
                        mod_kwargs["hook"].append(HookCls(**h_kwargs))

        usable_modules.append((mod_cls, mod_kwargs))

    # --- Loop regions and mods and run ---
    active_modules = []  # The batch queue
    for this_region in these_regions:
        for mod_cls, mod_kwargs in usable_modules:
            try:
                x_f = mod_cls(src_region=this_region, **mod_kwargs)

                if x_f is None:
                    continue

                r_str = f"{this_region[0]:.4f}/{this_region[1]:.4f}/{this_region[2]:.4f}/{this_region[3]:.4f}"
                logger.info(f"Running fetchez module {x_f.name} on region {r_str}...")

                x_f.run()

                count = len(x_f.results)
                logger.info(f"Found {count} data files from {mod_cls}.")

                if count > 0:
                    active_modules.append(x_f)

            except (KeyboardInterrupt, SystemExit, BrokenPipeError):
                logger.error("User interruption.")
                sys.exit(-1)
            except Exception:
                logger.error("Error running module", exc_info=True)

    if active_modules:
        try:
            core.run_fetchez(
                active_modules,
                threads=global_args.threads,
                global_hooks=global_hook_objs,
            )
        except (KeyboardInterrupt, SystemExit):
            logger.error("User breakage... please wait while fetchez exits.")
            sys.exit(0)

    else:
        logger.warning("No data found for any requested modules.")


if __name__ == "__main__":
    fetchez_cli()

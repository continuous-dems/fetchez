#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
fetchez.cli
~~~~~~~~~~~~~

This module contains the CLI for the Fetchez library.

:copyright: (c) 2010-2026 Regents of the University of Colorado
:license: MIT, see LICENSE for more details.
"""

import os
import sys
import logging
import argparse
import inspect
import signal
from typing import Dict, Optional, Any

from . import utils
from . import registry
from . import spatial
from . import core
from . import __version__

logger = logging.getLogger(__name__)


# =============================================================================
# CLI Decorator and Decorations and logging
# =============================================================================
def cli_opts(help_text: Optional[str] = None, **arg_help):
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


def print_banner_orbit():
    # C, B, G, R = "\033[36m", "\033[34m", "\033[32m", "\033[0m"
    print("""
    [ F E T C H E Z ]
    """)


print_welcome_banner = print_banner_orbit  # alias for when we randomly change it


def setup_logging(verbose=False):
    log_level = logging.INFO if verbose else logging.WARNING

    logger = logging.getLogger()
    logger.setLevel(log_level)

    if logger.hasHandlers():
        logger.handlers.clear()

    handler = utils.TqdmLoggingHandler()

    formatter = logging.Formatter("[ %(levelname)s ] %(name)s: %(message)s")
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


def _populate_subparser(
    subparser, module_cls, global_args=["self", "kwargs", "params"]
):
    """Introspect module __init__ to populate subparser arguments."""

    if not module_cls:
        return

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
def get_module_cli_desc(m: Dict) -> str:
    """Generates a formatted, categorized list of modules using Registry metadata."""

    CATEGORY_ORDER = [
        "Topography",
        "Bathymetry",
        "Oceanography",
        "Imagery",
        "Reference",
        "Generic",
    ]
    grouped_modules: Dict[Any, Any] = {}

    for key, val in m.items():
        cat = val.get("category", "Generic")
        if cat not in grouped_modules:
            grouped_modules[cat] = []

        desc = val.get("desc", f"Fetch data from {key}")
        grouped_modules[cat].append((key, desc))

    rows = []
    existing_cats = [c for c in CATEGORY_ORDER if c in grouped_modules]
    remaining_cats = sorted([c for c in grouped_modules if c not in CATEGORY_ORDER])

    for cat in existing_cats + remaining_cats:
        rows.append(f"\n\033[1;4m{cat}\033[0m")
        for name, desc in sorted(grouped_modules[cat], key=lambda x: x[0]):
            rows.append(f"  \033[1m{name:<18}\033[0m : {desc}")

    return "\n".join(rows)


class PrintModulesAction(argparse.Action):
    def __call__(self, parser, namespace, values, option_string=None):
        print_welcome_banner()
        print(f"""
        Supported fetchez modules (see {os.path.basename(sys.argv[0])} <module-name> --help for more info):

        {get_module_cli_desc(registry.FetchezRegistry._modules)}
        """)
        sys.exit(0)


def print_module_info(mod_key):
    """Pretty-print module metadata."""

    from .registry import FetchezRegistry

    meta = FetchezRegistry.get_info(mod_key)
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
    print(f"{'-' * 40}\n")


def parse_hook_arg(arg_str):
    """Parse a hook string into (name, kwargs).

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

    from .hooks.registry import HookRegistry

    active_instances = []
    if not hook_list_strs:
        return active_instances

    for h_str in hook_list_strs:
        name, kwargs = parse_hook_arg(h_str)

        HookCls = HookRegistry.get_hook(name)
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


# =============================================================================
# Command-line Interface(s) (CLI)
# =============================================================================
def fetchez_cli():
    """Run fetchez from command-line using argparse."""

    try:
        signal.signal(signal.SIGPIPE, signal.SIG_DFL)
    except AttributeError:
        # Windows does not strictly support SIGPIPE in the same way
        pass

    _usage = "%(prog)s [-R REGION] [OPTIONS] MODULE [MODULE-OPTS]..."

    registry.FetchezRegistry.load_user_plugins()
    registry.FetchezRegistry.load_installed_plugins()

    from .hooks.registry import HookRegistry
    from . import presets
    from . import config

    HookRegistry.load_builtins()
    HookRegistry.load_user_plugins()

    # user_presets = presets.load_user_presets()
    # user_presets = config.load_user_config().get('presets', {})
    user_presets = presets.get_global_presets()
    user_mod_presets = config.load_user_config().get("modules", {})

    # Check if first arg exists and ends in .json or yaml. -- project file --
    if (
        len(sys.argv) > 1
        and (sys.argv[1].endswith(".json") or sys.argv[1].endswith(".yaml"))
        and os.path.isfile(sys.argv[1])
    ):
        from . import project

        logging.basicConfig(
            level=logging.INFO,
            format="[ %(levelname)s ] %(name)s: %(message)s",
            stream=sys.stderr,
        )

        project_file = sys.argv[1]
        run = project.ProjectRun(project_file)
        run.run()
        sys.exit(0)

    parser = argparse.ArgumentParser(
        description=f"{utils.CYAN}%(prog)s{utils.RESET} ({__version__}) :: Discover and Fetch remote geospatial data",
        formatter_class=argparse.RawTextHelpFormatter,
        add_help=False,
        usage=_usage,
        epilog="""
Examples:
  fetchez -R -105/-104/39/40 srtm_plus
  fetchez -R loc:"Boulder, CO" copernicus --datatype=1
  fetchez charts --hook unzip --hook filename_filter:match=.000 --pipe-path
  fetchez --search bathymetry

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
        "-m",
        "--modules",
        nargs=0,
        action=PrintModulesAction,
        help="List all available data modules.",
    )
    disc_grp.add_argument(
        "-s",
        "--search",
        metavar="TERM",
        help="Search modules by tag, agency, or description.",
    )
    disc_grp.add_argument(
        "-i",
        "--info",
        metavar="MODULE",
        help="Show detailed metadata for a specific module.",
    )
    disc_grp.add_argument(
        "-h", "--help", action="store_true", help="Show this help message and exit."
    )
    disc_grp.add_argument(
        "-v", "--version", action="version", version=f"%(prog)s {__version__}"
    )

    exec_grp = parser.add_argument_group("Execution Control")
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
    # exec_grp.add_argument(
    #     "-z",
    #     "--no_check_size",
    #     action="store_true",
    #     help="Skip remote file size check if local file exists.",
    # )
    exec_grp.add_argument(
        "-q",
        "--quiet",
        action="store_true",
        help="Suppress progress bars and status messages.",
    )

    preset_grp = parser.add_argument_group("Pipeline Shortcuts (Hook Presets)")
    preset_grp.add_argument(
        "-l",
        "--list",
        action="store_true",
        help="List discovered URLs to stdout (Pre-Hook).",
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
    for name, defs in user_presets.items():
        flag_name = f"--{name}"
        help_text = defs.get("help", "Custom user preset.")
        preset_grp.add_argument(flag_name, action="store_true", help=help_text)

    adv_grp = parser.add_argument_group("Advanced Configuration")
    adv_grp.add_argument(
        "--hook",
        action="append",
        help="Add a custom global hook (e.g. 'audit:file=log.txt').",
    )
    adv_grp.add_argument(
        "--list-hooks", action="store_true", help="List all available hooks."
    )
    adv_grp.add_argument(
        "--hook-info",
        metavar="HOOK_NAME",
        type=str,
        help="Print detailed documentation and arguments for a specific hook.",
    )
    adv_grp.add_argument(
        "--init-presets",
        action="store_true",
        help="Generate a default ~/.fetchez/presets.json file.",
    )
    # adv_grp.add_argument('--init-presets', action='store_true', help="Export active presets to ./fetchez_presets_template.json (template for customization).")

    # Pre-process Arguments to fix argparses handling of -R
    fixed_argv = spatial.fix_argparse_region(sys.argv[1:])
    global_args, remaining_argv = parser.parse_known_args(fixed_argv)

    # check_size = not global_args.no_check_size

    # level = logging.WARNING if global_args.quiet else logging.INFO
    # I like sending logging to stderr, and anyway we want this with --pipe-path
    # logging.basicConfig(level=level, format='[ %(levelname)s ] %(name)s: %(message)s', stream=sys.stderr)
    setup_logging(
        not global_args.quiet
    )  # this prevents logging from distorting tqdm and leaving partial tqdm bars everywhere...

    if global_args.init_presets:
        presets.init_presets()
        sys.exit(0)

    if global_args.info:
        print_module_info(global_args.info)
        sys.exit(0)

    if global_args.search:
        results = registry.FetchezRegistry.search_modules(global_args.search)

        if not results:
            utils.echo_warning_msg(f'No modules found matching "{global_args.search}"')
            sys.exit(0)

        print(
            f'\nSearch results for "{utils.colorize(global_args.search, utils.CYAN)}":'
        )
        print("-" * 60)

        for mod_key in results:
            info = registry.FetchezRegistry.get_info(mod_key)
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
        from fetchez.hooks.registry import HookRegistry

        hook_cls = HookRegistry.get_hook(global_args.hook_info)
        if hook_cls:
            print(f"\n🪝  Hook: {hook_cls.name}")
            print(f"   Stage: {hook_cls.stage}")
            print(f"   Type:  {hook_cls.category}\n")

            import inspect

            doc = inspect.getdoc(hook_cls)
            if doc:
                print(doc)
            else:
                print("(No documentation available for this hook)")
            print("\n")
        else:
            print(f"❌ Hook '{global_args.hook_info}' not found.")
            print("   Run 'fetchez --list-hooks' to see available options.")

        sys.exit(0)

    if hasattr(global_args, "list_hooks") and global_args.list_hooks:
        print("\nAvailable Hooks:")
        print("=" * 60)

        # Group by category
        grouped_hooks = {}
        for name, cls_obj in HookRegistry._hooks.items():
            cat = getattr(cls_obj, "category", "uncategorized").lower()
            if cat not in grouped_hooks:
                grouped_hooks[cat] = []
            grouped_hooks[cat].append((name, cls_obj))

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
            print(f"\n[ {cat.title()} ]")

            for name, cls_obj in sorted(grouped_hooks[cat], key=lambda x: x[0]):
                desc = getattr(cls_obj, "desc", "No description")
                # stage = getattr(cls_obj, 'stage', 'file')
                print(f"  {utils.colorize(name, utils.BOLD):<18} : {desc}")

        print()
        sys.exit(0)

    # --- Init Global Hook Shortcuts ---
    global_hook_objs = []
    if hasattr(global_args, "hook") and global_args.hook:
        # global_hook_objs = init_hooks(global_args.hook)
        global_hook_objs.extend(init_hooks(global_args.hook))

    # --- Process Shortcuts ---
    for name, defs in user_presets.items():
        arg_attr = name.replace("-", "_")

        # load presets
        if getattr(global_args, arg_attr, False):
            chain = presets.hook_list_from_preset(defs)
            global_hook_objs.extend(chain)

    if global_args.list:
        from .hooks.basic import ListEntries, DryRun

        global_hook_objs.append(ListEntries())
        if not any(h.name == "dryrun" for h in global_hook_objs):
            global_hook_objs.append(DryRun())

    if global_args.inventory:
        from .hooks.basic import Inventory, DryRun

        fmt = global_args.inventory
        global_hook_objs.append(Inventory(format=fmt))
        if not any(h.name == "dryrun" for h in global_hook_objs):
            global_hook_objs.append(DryRun())

    if global_args.pipe_path:
        from .hooks.basic import PipeOutput

        global_hook_objs.append(PipeOutput())

    if global_args.audit_log:
        from .hooks.basic import Checksum, MetadataEnrich, Audit

        global_hook_objs.append(Checksum(algo="md5"))
        global_hook_objs.append(MetadataEnrich())
        global_hook_objs.append(Audit(file=global_args.audit_log))

    # --- Parse out modules/commands ---
    module_keys = {}
    for key, val in registry.FetchezRegistry._modules.items():
        module_keys[key] = key
        for alias in val.get("aliases", []):
            module_keys[alias] = key

    commands = []
    current_cmd = None
    current_args = []
    for arg in remaining_argv:
        is_module = (arg in module_keys) or (arg.split(":")[0] in module_keys)

        if is_module and not arg.startswith("-"):
            if current_cmd:
                commands.append((current_cmd, current_args))

            if len(arg.split(":")) > 1:
                _, raw_name, current_args = parse_fmod_argparse(arg)
                current_cmd = module_keys.get(raw_name, raw_name)
            else:
                current_cmd = module_keys.get(arg, arg)
                current_args = []
        else:
            if current_cmd and current_cmd != "file":
                current_args.append(arg)
            elif current_cmd == "file" and arg.startswith("-"):
                current_args.append(arg)
            elif os.path.isfile(arg):
                if current_cmd == "file":
                    if current_args and current_args[0].startswith("--paths="):
                        current_args[0] += f",{arg}"
                    else:
                        current_args.append(f"--paths={arg}")
                else:
                    current_cmd = "file"
                    current_args = [f"--paths={arg}"]
                # current_cmd = "file"
                # if current_args:
                #     current_args[0] += f",{arg}"
                # else:
                #     current_args = [f"--paths={arg}"]

    if current_cmd:
        commands.append((current_cmd, current_args))

    if global_args.help:
        if not commands:
            parser.print_help()
            sys.exit(0)
        else:
            commands[0][1].append("--help")

    if not commands:
        logger.error("You must select at least one module")
        parser.print_help()
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
        mod_cls = registry.FetchezRegistry.load_module(mod_key)
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
        active_presets.update(presets.get_module_presets(mod_key))
        if mod_key in user_mod_presets:
            user_mod_presets = user_mod_presets[mod_key].get("presets", {})
            # User presets overwrite built-in presets
            active_presets.update(user_mod_presets)

        if active_presets:
            mod_preset_grp = mod_parser.add_argument_group(f"{mod_key} Presets")

            for pname, pdef in active_presets.items():
                flag_name = f"--{pname}"
                help_text = pdef.get("help", f"Apply {mod_key} preset: {pname}")

                mod_preset_grp.add_argument(
                    flag_name, action="store_true", help=help_text
                )

        _populate_subparser(mod_parser, mod_cls)
        mod_args_ns = mod_parser.parse_args(mod_argv)
        mod_kwargs = vars(mod_args_ns)

        if mod_kwargs.get("outdir") is None:
            mod_kwargs["outdir"] = global_args.outdir

        if "mod_hook" in mod_kwargs and mod_kwargs["mod_hook"]:
            mod_kwargs["hook"] = init_hooks(mod_kwargs["mod_hook"])
        else:
            mod_kwargs["hook"] = []

        del mod_kwargs["mod_hook"]

        for pname, pdef in active_presets.items():
            arg_attr = pname.replace("-", "_")
            if getattr(mod_args_ns, arg_attr, False):
                chain = presets.hook_list_from_preset({"hooks": pdef["hooks"]})
                mod_kwargs["hook"].extend(chain)

            mod_kwargs.pop(arg_attr, None)

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
            # Depreciated threads/queue:
            # try:
            #     fr = core.fetch_results(
            #         x_f,
            #         n_threads=global_args.threads,
            #         check_size=check_size,
            #         attempts=global_args.attempts
            #     )
            #     fr.daemon = True
            #     fr.start()
            #     fr.join()
            # except (KeyboardInterrupt, SystemExit):
            #     logger.error('User breakage... please wait while fetchez exits.')
            #     x_f.status = -1
            #     while not fr.fetch_q.empty():
            #         try:
            #             fr.fetch_q.get(False)
            #             fr.fetch_q.task_done()
            #         except queue.Empty:
            #             break

        except (KeyboardInterrupt, SystemExit):
            logger.error("User breakage... please wait while fetchez exits.")
            sys.exit(0)

    else:
        logger.warning("No data found for any requested modules.")


if __name__ == "__main__":
    fetchez_cli()

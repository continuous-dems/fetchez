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
import queue
from typing import List, Dict, Optional, Union, Any, Tuple

from . import utils
from . import registry
from . import spatial
from . import core
from . import __version__

logger = logging.getLogger(__name__)

# =============================================================================
# CLI Decorator and Decorations and logging
# =============================================================================
def cli_opts(help_text: str = None, **arg_help):
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
    C, B, G, R = '\033[36m', '\033[34m', '\033[32m', '\033[0m'
    print(f"""
    [ F E T C H E Z ]
    """)

print_welcome_banner = print_banner_orbit # alias for when we randomly change it

def setup_logging(verbose=False):
    log_level = logging.INFO if verbose else logging.WARNING
    
    logger = logging.getLogger('geofetch')
    logger.setLevel(log_level)
    
    if logger.hasHandlers():
        logger.handlers.clear()

    handler = utils.TqdmLoggingHandler()
    
    formatter = logging.Formatter('[ %(levelname)s ] %(message)s')
    handler.setFormatter(formatter)
    
    logger.addHandler(handler)


# =============================================================================
# Argparse helpers
#
# Mostly based on cudem.factory
# =============================================================================
def parse_fmod_argparse(arg_str):
    """Parse 'module:key=val:key2=val2' strings."""
    parts = arg_str.split(':')
    mod_name = parts[0]
    args = []
    
    # If the string was just "module", parts is length 1
    # If "module:arg=1", parts is length 2+
    if len(parts) > 1:
        for p in parts[1:]:
            # Convert 'key=val' to '--key=val' for argparse consumption
            if '=' in p:
                k, v = p.split('=')
                args.append(f"--{k}={v}")
            else:
                # Handle boolean flags if passed as just ':flag'
                args.append(f"--{p}")
                
    return None, mod_name, args


def _populate_subparser(subparser, module_cls, global_args=['self', 'kwargs', 'params']):
    """Introspect module __init__ to populate subparser arguments."""
    
    if not module_cls: return

    sig = inspect.signature(module_cls.__init__)
    
    # Get help text from decorator if available
    arg_help = getattr(module_cls, '_cli_arg_help', {})
    
    for name, param in sig.parameters.items():
        # Skip base FetchModule arguments that are handled globally
        if name in ['self', 'kwargs', 'src_region', 'callback', 'outdir', 'name', 'params']:
            continue
            
        # Determine help string
        help_str = arg_help.get(name, f'Set {name} parameter')
        
        ## Determine type and default
        default = param.default
        if default is inspect.Parameter.empty:
            default = None
            
        # Handle Boolean Flags
        if param.annotation is bool or isinstance(default, bool):
            action = 'store_true' if not default else 'store_false'
            subparser.add_argument(f'--{name}', action=action, help=help_str)
        else:
            type_fn = None
            if param.annotation is int: type_fn = int
            elif param.annotation is float: type_fn = float
            
            subparser.add_argument(f'--{name}', default=default, type=type_fn, help=f"{help_str} (default: {default})")


# =============================================================================
# Argument Pre-processing to account for negative coordinates at the
# beginning of the region. argparse otherwise would think it was a new
# argument; breaking the sometimes prefered syntax.
# =============================================================================
def fix_argparse_region(raw_argv):
    fixed_argv = []
    i = 0
    while i < len(raw_argv):
        arg = raw_argv[i]
        
        ## Check if this is a region flag and there is a next argument
        if arg in ['-R', '--region', '--aoi'] and i + 1 < len(raw_argv):
            next_arg = raw_argv[i+1]
            if next_arg.startswith('-'):
                if arg == '-R':
                    fixed_argv.append(f"{arg}{next_arg}")
                else:
                    fixed_argv.append(f"{arg}={next_arg}")
                i += 2
                continue

        fixed_argv.append(arg)
        i += 1
    return fixed_argv
        
    
# =============================================================================
# Registry & Help Helpers
# =============================================================================
def get_module_cli_desc(m: Dict) -> str:
    """Generates a formatted, categorized list of modules using Registry metadata."""
    
    CATEGORY_ORDER = ['Topography', 'Bathymetry', 'Oceanography', 'Imagery', 'Reference', 'Generic']
    grouped_modules = {}
    
    for key, val in m.items():
        cat = val.get('category', 'Generic')
        if cat not in grouped_modules:
            grouped_modules[cat] = []
            
        desc = val.get('desc', f'Fetch data from {key}')
        grouped_modules[cat].append((key, desc))

    rows = []
    existing_cats = [c for c in CATEGORY_ORDER if c in grouped_modules]
    remaining_cats = sorted([c for c in grouped_modules if c not in CATEGORY_ORDER])
    
    for cat in existing_cats + remaining_cats:
        rows.append(f'\n\033[1;4m{cat}\033[0m')
        for name, desc in sorted(grouped_modules[cat], key=lambda x: x[0]):
            rows.append(f'  \033[1m{name:<18}\033[0m : {desc}')

    return '\n'.join(rows)


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

    print(f'\n{utils.CYAN}MODULE: {mod_key.upper()}{utils.RESET}')
    print(f'{"-"*40}')
    print(f'  Description : {meta.get("desc", "N/A")}')
    print(f'  Provider    : {meta.get("agency", "Unknown")}')
    print(f'  Category    : {meta.get("category", "Generic")}')
    print(f'  Coverage    : {meta.get("region", "Unknown")}')
    print(f'  Resolution  : {meta.get("resolution", "Unknown")}')
    print(f'  License     : {meta.get("license", "Unknown")}')
    print(f'  Tags        : {", ".join(meta.get("tags", []))}')
    
    if 'urls' in meta:
        print(f"\n  Links:")
        for k, v in meta['urls'].items():
            print(f"    {k:<10}: {v}")
    print(f"{'-'*40}\n")

    
# =============================================================================
# Command-line Interface(s) (CLI)
# =============================================================================
def fetchez_cli():
    """Run fetchez from command-line using argparse."""

    _usage = f'%(prog)s [-R REGION] [-H THREADS] [-A ATTEMPTS] [-l] [-z] [-q] [-v] [-m] [-n] [-s] [-i] MODULE [MODULE-OPTS]...' 

    registry.FetchezRegistry.load_user_plugins()

    parser = argparse.ArgumentParser(
        description=f'{utils.CYAN}%(prog)s{utils.RESET} ({__version__}) :: Discover and Fetch remote geospatial data',
        formatter_class=argparse.RawTextHelpFormatter,
        add_help=False,
        usage=_usage,
        epilog=f"""CUDEM home page: <http://cudem.colorado.edu>"""
    )

    parser.add_argument('-R', '--region', '--aoi', action='append', help=spatial.region_help_msg())
    parser.add_argument('-H', '--threads', type=int, default=1, help='Set the number of threads (default: 1)')
    parser.add_argument('-A', '--attempts', type=int, default=5, help='Set the number of fetching attempts (default: 5)')
    parser.add_argument('-B', '--buffer', type=float, default=0, metavar='PERCENT', help='Buffer the input region(s) by a percentage (e.g., 5 for 5 percent).')
    parser.add_argument('-i', '--info', metavar='MODULE', help='Show detailed info about a specific module')
    parser.add_argument('-s', '--search', metavar='TERM', help='Search modules by tag, agency, license, etc.')
    parser.add_argument('-l', '--list', action='store_true', help='Return a list of fetch URLs in the given region.')
    parser.add_argument('-z', '--no_check_size', action='store_true', help='Don\'t check the size of remote data if local data exists.')
    parser.add_argument('-q', '--quiet', action='store_true', help='Lower the verbosity to a quiet')
    parser.add_argument('-m', '--modules', nargs=0, action=PrintModulesAction, help='Display the available modules')
    parser.add_argument('-n', '--inventory', action='store_true', help='Generate a data inventory, don\'t download any data')
    parser.add_argument('-p', '--pipe-path', action='store_true', help='Print the absolute path of fetched files to stdout (useful for piping).')
    parser.add_argument('-v', '--version', action='version', version=f'%(prog)s {__version__}')
    
    # Pre-process Arguments to fix argparses handling of -R
    fixed_argv = fix_argparse_region(sys.argv[1:])
    global_args, remaining_argv = parser.parse_known_args(fixed_argv)
      
    check_size = not global_args.no_check_size
    
    level = logging.WARNING if global_args.quiet else logging.INFO
    # I like sending logging to stderr, and anyway we want this with --pipe-path
    logging.basicConfig(level=level, format='[ %(levelname)s ] %(name)s: %(message)s', stream=sys.stderr)
    setup_logging() # this prevents logging from distorting tqdm and leaving partial tqdm bars everywhere...

    if global_args.info:
        print_module_info(global_args.info)
        sys.exit(0)

    if global_args.search:
        results = registry.FetchezRegistry.search_modules(global_args.search)
        
        if not results:
            utils.echo_warning_msg(f'No modules found matching "{global_args.search}"')
            sys.exit(0)
            
        print(f'\nSearch results for "{utils.colorize(global_args.search, utils.CYAN)}":')
        print('-' * 60)
        
        for mod_key in results:
            info = registry.FetchezRegistry.get_info(mod_key)
            desc = info.get('desc', 'No description')
            agency = info.get('agency', '')
            
            print(f'{utils.colorize(mod_key, utils.BOLD):<15} {utils.colorize(f"[{agency}]", utils.YELLOW):<10} {desc}')
            
            tags = ", ".join(info.get('tags', [])[:5]) # limit to 5 tags
            if tags: print(f'    ↳ tags: {tags}')
            
        print("-" * 60)
        sys.exit(0)
        
    module_keys = {}
    for key, val in registry.FetchezRegistry._modules.items():
        module_keys[key] = key
        for alias in val.get('aliases', []):
            module_keys[alias] = key

    commands = []
    current_cmd = None
    current_args = []

    for arg in remaining_argv:
        is_module = (arg in module_keys) or (arg.split(':')[0] in module_keys)
        
        if is_module and not arg.startswith('-'):
            if current_cmd:
                commands.append((current_cmd, current_args))
            
            if len(arg.split(':')) > 1:
                # Use local parse function
                _, raw_name, current_args = parse_fmod_argparse(arg)
                # Resolve alias if necessary
                current_cmd = module_keys.get(raw_name, raw_name) 
            else:
                current_cmd = module_keys.get(arg, arg)
                current_args = []
        else:
            if current_cmd:
                current_args.append(arg)

    if current_cmd:
        commands.append((current_cmd, current_args))

    if not commands:
        parser.print_help()
        sys.exit(0)

    if not global_args.region:
        these_regions = [(-180, 180, -90, 90)]
    else:
        # Spatial returns tuples now, not Objects
        these_regions = spatial.parse_region(global_args.region)

    if global_args.buffer > 0:
        these_regions = [spatial.buffer_region(r, global_args.buffer) for r in these_regions]
        
    usable_modules = []
    for mod_key, mod_argv in commands:
        
        # LOAD MODULE HERE
        mod_cls = registry.FetchezRegistry.load_module(mod_key)
        
        if mod_cls is None:
            logger.error(f'Could not load module: {mod_key}')
            continue

        mod_parser = argparse.ArgumentParser(
            prog=f'fetchez [OPTIONS] {mod_key}',
            description=mod_cls.__doc__,
            add_help=True,
            formatter_class=argparse.RawTextHelpFormatter
        )

        _populate_subparser(mod_parser, mod_cls)

        mod_args_ns = mod_parser.parse_args(mod_argv)
        mod_kwargs = vars(mod_args_ns)
        usable_modules.append((mod_cls, mod_kwargs))
    
    for this_region in these_regions:
        # Output the data inventory if requested.
        # Update in the future to allow for different outputs, 'csv' or 'geojson'
        # we will need to update core.inventory and module results to give us
        # some kind of geometry...
        if global_args.inventory:
            modules = []
            for mod_cls, mod_kwargs in usable_modules:
                x_f = mod_cls(
                    src_region=this_region,
                    **mod_kwargs  
                )
                
                if x_f is None: continue                
                modules.append(x_f)

            report = core.inventory(modules, this_region, out_format='csv')
            print(report)
            continue
        
        for mod_cls, mod_kwargs in usable_modules:
            try:
                x_f = mod_cls(
                    src_region=this_region,
                    **mod_kwargs  
                )
                
                if x_f is None: continue

                r_str = f'{this_region[0]:.4f}/{this_region[1]:.4f}/{this_region[2]:.4f}/{this_region[3]:.4f}'
                logger.info(f'Running fetchez module {x_f.name} on region {r_str}...')

                x_f.run()

                logger.info(f'Found {len(x_f.results)} data files.')

                if not x_f.results:
                    continue

                if global_args.list:
                    for result in x_f.results:
                        print(result['url'])
                else:
                    try:
                        # run_fetchez expects a list of modules, so we wrap x_f in brackets [x_f].
                        # It handles the progress bar and threading internally.
                        core.run_fetchez([x_f], threads=global_args.threads, pipe_path=global_args.pipe_path)

                    except (KeyboardInterrupt, SystemExit):
                        logger.error('User breakage... please wait while fetchez exits.')
                        # No need to manually drain queues anymore; Python's executor handles cleanup.
                        sys.exit(0)
                    # depreciated threads/queue
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
                logger.error('User interruption.')
                sys.exit(-1)
            except Exception:
                logger.error(f'Error running module', exc_info=True)

                
if __name__ == '__main__':
    fetchez_cli()

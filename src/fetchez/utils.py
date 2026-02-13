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
import tqdm

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
UNDERLINE = "\033[4m"
REVERSE = "\033[7m"


# =============================================================================
# Terminal Printing Helpers
#
# Some of these are holdouts from cudem.utils that were used extensively by
# fetches modules. We're keeping them (or them-like) around for a while
# for backward compatability. It is now prefered to use logging instead of
# these `echo` functions.
# =============================================================================
def colorize(text: str, color: str) -> str:
    """Wrap text in ANSI color codes."""

    return f"{color}{text}{RESET}"


def echo_msg(msg: str, leading_line: bool = False):
    """Print a standard message (alias for print, compatible with scripts)."""

    if leading_line:
        print("")
    print(msg)


def echo_error_msg(msg: str, prefix: str = "[ ERROR ]"):
    """Print a standardized error message to stderr."""

    sys.stderr.write(f"{RED}{BOLD}{prefix}{RESET} {msg}\n")


def echo_warning_msg(msg: str, prefix: str = "[ WARNING ]"):
    """Print a standardized warning message."""

    print(f"{YELLOW}{BOLD}{prefix}{RESET} {msg}")


def echo_success_msg(msg: str, prefix: str = "[ OK ]"):
    """Print a standardized success message."""

    print(f"{GREEN}{BOLD}{prefix}{RESET} {msg}")


def echo_highlight(msg: str):
    """Print a bold/highlighted message."""

    print(f"{BOLD}{msg}{RESET}")


class TqdmLoggingHandler(logging.Handler):
    """A logging handler that outputs to tqdm.write() to avoid
    interfering with tqdm progress bars.
    """

    def __init__(self, level=logging.NOTSET):
        super().__init__(level)

    def emit(self, record):
        try:
            msg = self.format(record)
            tqdm.tqdm.write(msg)
            self.flush()
        except Exception:
            self.handleError(record)


# =============================================================================
# Data, Type and File Helpers
# =============================================================================
def this_date():
    """Get current date."""

    return datetime.datetime.now().strftime("%Y%m%d%H%M%S")


def get_username():
    username = ""
    while not username:
        username = input("username: ")
    return username


def get_password():
    password = ""
    while not password:
        password = getpass.getpass("password: ")
    return password


def int_or(val, or_val=None):
    """Return val if val is an integer, else return or_val"""

    try:
        return int(float_or(val))
    except:
        return or_val


def float_or(val, or_val=None):
    """Return val if val is a float, else return or_val"""

    try:
        return float(val)
    except:
        return or_val


def str_or(instr, or_val=None, replace_quote=True):
    """Return val if val is a string, else return or_val"""

    if instr is None:
        return or_val
    try:
        s = str(instr)
        return s.replace('"', "") if replace_quote else s
    except:
        return or_val


def str2bool(v):
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


def str_truncate_middle(s, n=50):
    """Truncate the middle of the input string, replace with `...`"""

    if len(s) <= n:
        return s

    n_2 = int(n) // 2 - 2
    return f"{s[:n_2]}...{s[-n_2:]}"


def inc2str(inc):
    """Convert a WGS84 geographic increment to a string identifier."""

    return str(fractions.Fraction(str(inc * 3600)).limit_denominator(10)).replace(
        "/", ""
    )


def str2inc(inc_str):
    """Convert a GMT-style inc_str (e.g. 6s) to geographic units.

    c/s - arc-seconds
    m - arc-minutes
    """

    if inc_str is None or str(inc_str).lower() == "none" or len(str(inc_str)) == 0:
        return None

    inc_str = str(inc_str)
    units = inc_str[-1]

    try:
        if units == "c" or units == "s":
            return float(inc_str[:-1]) / 3600.0
        elif units == "m":
            return float(inc_str[:-1]) / 360.0
        else:
            return float(inc_str)
    except ValueError as e:
        echo_error_msg(f"Could not parse increment {inc_str}: {e}")
        return None


def remove_glob(pathname: str):
    """Safely remove files matching a glob pattern."""

    import glob

    for p in glob.glob(pathname):
        if os.path.exists(p):
            try:
                os.remove(p)
            except OSError as e:
                logger.error(f"Could not remove {p}: {e}")


def make_temp_fn(basename, temp_dir=None):
    """Generate a temporary filename."""

    prefix = os.path.splitext(basename)[0]
    suffix = os.path.splitext(basename)[1]
    fd, path = tempfile.mkstemp(suffix=suffix, prefix=f"{prefix}_", dir=temp_dir)
    os.close(fd)
    return path


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


def range_pairs(lst):
    return [(lst[i], lst[i + 1]) for i in range(len(lst) - 1)]


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
    if not os.path.exists(outdir):
        os.makedirs(outdir)

    extracted_files = []

    try:
        with zipfile.ZipFile(src_fn, "r") as z:
            want_exts = [
                e.lower() if e.startswith(".") else f".{e.lower()}" for e in ext
            ]

            for file_info in z.infolist():
                if file_info.is_dir():
                    continue

                _, f_ext = os.path.splitext(file_info.filename)
                if f_ext.lower() in want_exts:
                    filename = os.path.basename(file_info.filename)
                    target_path = os.path.join(outdir, filename)

                    if verbose:
                        logger.info(f"Extracting {filename}...")

                    with z.open(file_info) as source, open(target_path, "wb") as target:
                        shutil.copyfileobj(source, target)

                    extracted_files.append(target_path)

    except zipfile.BadZipFile:
        if verbose:
            logger.error(f"Bad Zip File: {src_fn}")
    except Exception as e:
        if verbose:
            logger.error(f"Unzip error {src_fn}: {e}")

    return extracted_files


def p_f_unzip(src_file, fns=None, outdir="./", tmp_fn=False):
    """Unzip specific files from src_file based on matches in `fns`."""

    if fns is None:
        fns = []

    extracted_paths = []
    ext = os.path.splitext(src_file)[1].lower()

    if ext == ".zip":
        with zipfile.ZipFile(src_file, "r") as z:
            namelist = z.namelist()
            for pattern in fns:
                for member in namelist:
                    # Match pattern in the base filename
                    if pattern in os.path.basename(member):
                        if member.endswith("/"):  # Skip directories
                            continue

                        dest_fn = os.path.join(outdir, os.path.basename(member))
                        if tmp_fn:
                            dest_fn = make_temp_fn(member, temp_dir=outdir)

                        # Extract and write the file
                        with open(dest_fn, "wb") as f:
                            f.write(z.read(member))

                        extracted_paths.append(dest_fn)
                        logger.info(f"Extracted: {member} to {dest_fn}")
    else:
        # Fallback if the file isn't a zip
        for pattern in fns:
            if pattern == os.path.basename(src_file):
                extracted_paths.append(src_file)
                break

    return extracted_paths


# =============================================================================
# Hooks
# =============================================================================
def merge_hooks(global_hooks, local_hooks):
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

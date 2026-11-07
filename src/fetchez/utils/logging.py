#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
fetchez.utils.logging
~~~~~~~~~~~~~~~~

Logging configuration for Fetchez.

:copyright: (c) 2012 - 2026 CIRES Coastal DEM Team
:license: MIT, see LICENSE for more details.
"""

import sys
from pathlib import Path
from tqdm.auto import tqdm
import logging
from typing import Optional

from .misc import str_or, int_or


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


def configure_logging(
    name="fetchez",
    *,
    quiet=False,
    verbose=False,
    level=None,
    handler=None,
    propagate=True,
):
    if level is None:
        level = logging.WARNING if quiet else logging.DEBUG if verbose else logging.INFO

    logger = logging.getLogger(name)
    logger.setLevel(level)
    logger.propagate = propagate

    for existing in logger.handlers[:]:
        if getattr(existing, "_fetchez_managed", False):
            logger.removeHandler(existing)
            existing.close()

    if handler is None:
        handler = TqdmLoggingHandler()

    handler.setFormatter(logging.Formatter("[ %(levelname)s ] %(name)s: %(message)s"))
    handler._fetchez_managed = True
    logger.addHandler(handler)

    return logger


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

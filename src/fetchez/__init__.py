# -*- coding: utf-8 -*-

__version__ = "0.4.2"
__author__ = "Matthew Love"
__credits__ = "CIRES"

# Import everything except the individual modules.
from . import fred
from . import core
from . import spatial
from . import registry

__all__ = ["core", "fred", "spatial", "registry"]

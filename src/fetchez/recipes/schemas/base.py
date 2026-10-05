#!/usr/bin/env python

"""
fetchez.recipes.schemas.base
~~~~~~~~~~~~~~

Generic Schema Registry for the Fetchez Recipe Engine.
Allows external domains (like Globato) to register
custom recipe validations.

:copyright: (c) 2010-2026 Regents of the University of Colorado
:license: MIT, see LICENSE for more details.
"""

import logging

logger = logging.getLogger(__name__)


class BaseSchema:
    """The generic base class for all recipe schemas."""

    name = "base"

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.errors = []

    def validate(self, config):
        """Subclasses must override this to inject their domain-specific rules.
        Append any error strings to self.errors.
        """

    def run(self, config):
        """executes the validation and returns the standardized output."""

        self.errors = []  # Reset state on run
        self.validate(config)
        return len(self.errors) == 0, self.errors

#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
fetchez.schema
~~~~~~~~~~~~~~
Generic Schema Registry for the Fetchez Recipe Engine.
Allows external domains (like Globato) to register
custom recipe mutators.

:copyright: (c) 2010-2026 Regents of the University of Colorado
:license: MIT, see LICENSE for more details.
"""

from typing import Any
import logging

logger = logging.getLogger(__name__)


class BaseSchema:
    """The generic base class for all recipe schemas."""

    name = "base"

    @classmethod
    def apply(cls, config):
        """Mutates and returns the recipe config.
        Subclasses must override this to inject their domain-specific rules.
        """

        return config


class SchemaRegistry:
    """Holds all registered schemas."""

    _schemas: dict[Any, Any] = {}

    @classmethod
    def register(cls, schema_class):
        """Allows external libraries to register their schemas."""

        cls._schemas[schema_class.name.lower()] = schema_class
        logger.debug(f"Registered schema: {schema_class.name}")

    @classmethod
    def apply_schema(cls, config):
        """Looks for a schema in the config and applies its rules."""

        schema_name = config.get("domain", {}).get("schema")

        if schema_name:
            schema_name = schema_name.lower()
            if schema_name in cls._schemas:
                logger.info(f"Applying '{schema_name}' schema rules to recipe...")
                SchemaCls = cls._schemas[schema_name]
                return SchemaCls.apply(config)
            else:
                logger.warning(
                    f"Schema '{schema_name}' requested but not registered. Ignoring."
                )

        return config

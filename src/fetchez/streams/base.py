#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
fetchez.streams.base
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Base fetchez Reader class to create 'streams'

:copyright: (c) 2016 - 2026 Regents of the University of Colorado
:license: MIT, see LICENSE for more details.
"""

import queue
import threading
import inspect

from fetchez.core import run_fetchez
from fetchez.utils import parse_hook_string
from fetchez.hooks import FetchHook


class QueueSinkHook(FetchHook):
    """An internal hook that yields stream chunks to a Queue."""

    name = "queue_sink"
    meta_stage = "stream"

    def __init__(self, q):
        super().__init__()
        self.q = q
        # The first exception a stream raised while being read, as the reader
        # raised it; run_fetchez() only re-raises it wrapped in a RuntimeError.
        self.error = None

    def run(self, entries):
        for _mod, entry in entries:
            stream = entry.get("stream")
            if stream:
                # Intercept the generator
                def interceptor(s):
                    try:
                        for chunk in s:
                            self.q.put(chunk)
                            yield chunk
                    except Exception as e:
                        if self.error is None:
                            self.error = e
                        raise

                entry["stream"] = interceptor(stream)
        return entries


class BaseStream:
    """Lazy Fetchez stream.

    Recipe-backed streams compile each iteration. ``modules=`` remains
    supported for direct callers of the older API.
    """

    def __init__(
        self,
        modules=None,
        region=None,
        ignore_failures=False,
        *,
        recipe=None,
        context=None,
    ):
        if recipe is None and modules is None:
            raise ValueError("BaseStream requires modules or a recipe")
        self.recipe = recipe
        self.context = context
        self.modules = modules if modules is not None else []
        self.region = region
        self.global_hooks = []  # Legacy direct-module path.
        self.hook_definitions = []  # Recipe-backed, declarative path.
        self.ignore_failures = ignore_failures

    def pipe(self, hook_or_string, **kwargs):
        """Append a processing hook; defer resolution for Recipe streams."""
        from fetchez.registry import HookRegistry, PresetRegistry

        if self.recipe is not None:
            if isinstance(hook_or_string, str):
                parsed = parse_hook_string(hook_or_string)
                name = parsed.get("name")
                PresetRegistry.load_all()
                if PresetRegistry.get_preset(name):
                    # Preserve the existing preset override form, deferring
                    # expansion and hook instantiation until compilation.
                    overrides = {**parsed.get("args", {}), **kwargs}
                    definition = {"preset": name}
                    if overrides:
                        definition["args"] = [
                            {"name": key, "args": value}
                            for key, value in overrides.items()
                        ]
                else:
                    definition = {
                        "name": name,
                        "args": {
                            **parsed.get("args", {}),
                            **kwargs,
                        },
                    }
            elif isinstance(hook_or_string, dict):
                definition = dict(hook_or_string)
                if not (definition.get("name") or definition.get("preset")):
                    raise ValueError(f"Invalid hook definition: {definition!r}")
                if kwargs:
                    definition["args"] = {**definition.get("args", {}), **kwargs}
            elif inspect.isclass(hook_or_string) or isinstance(
                hook_or_string, FetchHook
            ):
                if kwargs:
                    if not inspect.isclass(hook_or_string):
                        raise ValueError(
                            "Cannot override arguments of an existing hook"
                        )
                    definition = {"name": hook_or_string, "args": kwargs}
                else:
                    definition = hook_or_string
            else:
                raise TypeError(f"Unsupported hook definition: {hook_or_string!r}")

            self.hook_definitions.append(definition)
            return self

        # Backward-compatible direct-module API.
        if isinstance(hook_or_string, str):
            PresetRegistry.load_all()
            if PresetRegistry.get_preset(hook_or_string):
                override_def = [
                    {
                        "preset": hook_or_string,
                        "args": [{"name": k, "args": v} for k, v in kwargs.items()],
                    }
                ]
                self.global_hooks.extend(
                    PresetRegistry.hook_list_from_preset(override_def)
                )
                return self
            hook_config = parse_hook_string(hook_or_string)
            HookRegistry.load_all()
            hook_class = HookRegistry.get_class(hook_config.get("name"))
            if hook_class is None:
                raise ValueError(f"Hook '{hook_or_string}' not found.")
            self.global_hooks.append(
                hook_class(
                    **{
                        **hook_config.get("args", {}),
                        **kwargs,
                    }
                )
            )
        elif isinstance(hook_or_string, dict):
            HookRegistry.load_all()
            hook_name = hook_or_string.get("name")
            hook_class = HookRegistry.get_class(hook_name)
            if hook_class is None:
                raise ValueError(f"Invalid hook definition: {hook_or_string!r}")
            self.global_hooks.append(hook_class(**hook_or_string.get("args", {})))
        else:
            hook = (
                hook_or_string
                if hasattr(hook_or_string, "run")
                else hook_or_string(**kwargs)
            )
            self.global_hooks.append(hook)
        return self

    def __iter__(self):
        """Compile and yield chunks using the existing queue-sink protocol."""
        if self.recipe is not None:
            # Never mutate the original Recipe across iterations. Existing
            # class definitions yield new objects; instances remain by identity.
            from fetchez.recipe import Recipe, _safe_config_copy

            config = _safe_config_copy(self.recipe.config)
            config["global_hooks"] = list(config.get("global_hooks", [])) + list(
                self.hook_definitions
            )
            if self.context is not None and self.context.shared_cache is not None:
                self.context.shared_cache.mkdir(parents=True, exist_ok=True)
            plan = Recipe(config, base_dir=self.recipe.recipe_dir).compile(
                self.context, ignore_failures=self.ignore_failures
            )
            modules = plan.modules
            hooks = list(plan.global_hooks)
        else:
            plan = None
            modules = self.modules
            hooks = list(self.global_hooks)
            for mod in modules:
                mod.run()

        chunk_queue = queue.Queue(maxsize=100)
        sink = QueueSinkHook(chunk_queue)
        hooks.append(sink)
        DONE = object()
        worker_error = []

        def background_worker():
            try:
                if plan is not None:
                    plan.global_hooks = hooks
                    plan.execute()
                else:
                    run_fetchez(
                        modules,
                        threads=2,
                        global_hooks=hooks,
                        ignore_failures=self.ignore_failures,
                    )
            except Exception as exc:
                worker_error.append(exc)
            finally:
                chunk_queue.put(DONE)

        worker = threading.Thread(target=background_worker, daemon=True)
        worker.start()
        while True:
            chunk = chunk_queue.get()
            if chunk is DONE:
                break
            yield chunk
            chunk_queue.task_done()

        if worker_error and not self.ignore_failures:
            error = worker_error[0]
            if sink.error is not None and error.__cause__ is sink.error:
                raise sink.error
            raise error

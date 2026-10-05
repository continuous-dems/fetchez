#!/usr/bin/env python

"""
fetchez.streams.base
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Base fetchez Reader class to create 'streams'

:copyright: (c) 2016 - 2026 Regents of the University of Colorado
:license: MIT, see LICENSE for more details.
"""

import queue
import threading

from fetchez.core import run_fetchez
from fetchez.hooks import FetchHook
from fetchez.utils import parse_hook_string


class QueueSinkHook(FetchHook):
    """An internal hook that yields stream chunks to a Queue."""

    name = "queue_sink"
    meta_stage = "stream"

    def __init__(self, q):
        super().__init__()
        self.q = q

    def run(self, entries):
        for _mod, entry in entries:
            stream = entry.get("stream")
            if stream:
                # Intercept the generator
                def interceptor(s):
                    for chunk in s:
                        self.q.put(chunk)
                        yield chunk

                entry["stream"] = interceptor(stream)
        return entries


class BaseStream:
    def __init__(self, modules, region=None, ignore_failures=False):
        self.modules = modules
        self.region = region
        self.global_hooks = []
        self.ignore_failures = ignore_failures

    def pipe(self, hook_or_string, **kwargs):
        """Chain a processing hook onto the pipeline."""

        from fetchez.registry import HookRegistry, PresetRegistry

        if isinstance(hook_or_string, str):
            PresetRegistry.load_all()
            if PresetRegistry.get_preset(hook_or_string):
                override_def = [
                    {
                        "preset": hook_or_string,
                        "args": [{"name": k, "args": v} for k, v in kwargs.items()],
                    }
                ]
                hooks = PresetRegistry.hook_list_from_preset(override_def)
                for h in hooks:
                    self.global_hooks.append(h)
                return self

            hook_config = parse_hook_string(hook_or_string)
            HookRegistry.load_all()
            hook_class = HookRegistry.get_class(hook_config.get("name"))

            if not hook_class:
                raise ValueError(f"Hook '{hook_or_string}' not found.")

            kwargs = {**hook_config.get("args", {}), **kwargs}
            self.global_hooks.append(hook_class(**kwargs))

        elif isinstance(hook_or_string, dict):
            HookRegistry.load_all()
            PresetRegistry.load_all()

            hook_name = hook_or_string.get("name") or hook_or_string.get("preset")
            if hook_name:
                hook_class = HookRegistry.get_class(hook_name)
                self.global_hooks.append(hook_class(**hook_or_string.get("args", {})))
            else:
                raise ValueError(f"Invalid hook definition: {hook_or_string}.")

        else:
            hook = (
                hook_or_string
                if hasattr(hook_or_string, "run")
                else hook_or_string(**kwargs)
            )
            self.global_hooks.append(hook)

        return self

    def __iter__(self):
        """Yield chunks using a background pipeline thread."""

        [mod.run() for mod in self.modules]
        chunk_queue = queue.Queue(maxsize=100)
        sink = QueueSinkHook(chunk_queue)

        run_hooks = self.global_hooks + [sink]

        DONE = object()

        def background_worker():
            try:
                run_fetchez(
                    self.modules,
                    threads=2,
                    global_hooks=run_hooks,
                    ignore_failures=self.ignore_failures,
                )
            finally:
                chunk_queue.put(DONE)

        # Start the engine in the background
        t = threading.Thread(target=background_worker, daemon=True)
        t.start()

        while True:
            chunk = chunk_queue.get()
            if chunk is DONE:
                break
            yield chunk
            chunk_queue.task_done()

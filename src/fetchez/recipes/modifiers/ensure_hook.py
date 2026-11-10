#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
fetchez.recipes.modifiers.ensure_hook
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Generic, opt-in recipe modifier for conditional companion-hook insertion.

Runs on expanded recipe definitions before hook instantiation. This does not
interpret meta_requires, expand newly inserted presets, or change hook stages.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any
import logging

from fetchez.recipes.modifiers import BaseModifier

logger = logging.getLogger(__name__)


def _name(spec: Any) -> str | None:
    name = (
        spec.get("name") if isinstance(spec, Mapping) else getattr(spec, "name", None)
    )
    return name.replace("_", "-") if isinstance(name, str) else None


def _args(spec: Any) -> Mapping[str, Any]:
    if isinstance(spec, Mapping):
        args = spec.get("args") or {}
        if not isinstance(args, Mapping):
            raise TypeError("Hook args must be a mapping")

        return args
    return {}  # Do not infer constructor args from arbitrary runtime objects.


def _match(spec: Any, selector: Mapping[str, Any]) -> bool:
    wanted = selector.get("hook", selector.get("name"))
    if wanted is not None and _name(spec) != str(wanted).replace("_", "-"):
        return False

    if "id" in selector:
        actual_id = (
            spec.get("id") if isinstance(spec, Mapping) else getattr(spec, "id", None)
        )
        if actual_id != selector["id"]:
            return False

    wanted_args = selector.get("args") or {}
    if not isinstance(wanted_args, Mapping):
        raise TypeError("when.args must be a mapping")

    actual_args = _args(spec)
    if isinstance(spec, Mapping):
        return all(
            k in actual_args and actual_args[k] == v for k, v in wanted_args.items()
        )

    # Allow explicit public attributes for a preconfigured Python hook instance,
    # but never synthesize missing attributes or introspect private state.
    return all(
        hasattr(spec, k) and getattr(spec, k) == v for k, v in wanted_args.items()
    )


def _iter_requesters(config: Mapping[str, Any]):
    for hook in config.get("global_hooks") or ():
        yield None, hook
    for module in config.get("modules") or ():
        hooks = (
            module.get("hooks") or ()
            if isinstance(module, Mapping)
            else getattr(module, "hooks", ())
        )
        for hook in hooks:
            yield module, hook


def _contains_target(
    hooks: list[Any], name: str, args: Mapping[str, Any], target_id: Any
) -> bool:
    for existing in hooks:
        if _name(existing) != name:
            continue

        existing_id = (
            existing.get("id")
            if isinstance(existing, Mapping)
            else getattr(existing, "id", None)
        )
        if target_id is not None and existing_id != target_id:
            continue

        if isinstance(existing, Mapping):
            if all(
                k in _args(existing) and _args(existing)[k] == v
                for k, v in args.items()
            ):
                return True

        elif not args:  # No reliable constructor-arg reflection on hook objects.
            return True

    return False


class EnsureHook(BaseModifier):
    """Ensure a concrete hook when an expanded recipe hook matches a selector.

    ``when`` matches hook name, optional instance id, and exact args.
    ``ensure`` specifies name, optional id/args, scope (global or module),
    and position (append or prepend). ``forward_args`` forwards named values
    from the requester. ``set_defaults`` fills absent/None requester arguments.

    Stage selection belongs to the registered hook, not the modifier.
    """

    name = "ensure-hook"
    meta_category = "workflow"
    meta_desc = "Conditionally ensure a companion hook in an expanded recipe."

    def __init__(
        self,
        when: Mapping[str, Any],
        ensure: Mapping[str, Any],
        forward_args: list[str] | tuple[str, ...] = (),
        set_defaults: Mapping[str, Any] | None = None,
        **kwargs: Any,
    ):
        super().__init__(**kwargs)
        self.when = dict(when)
        self.ensure = dict(ensure)
        self.forward_args = tuple(forward_args)
        self.set_defaults = dict(set_defaults or {})
        if not self.when or not any(k in self.when for k in ("hook", "name", "id")):
            raise ValueError("when must identify a hook by name or id")

        if not isinstance(self.ensure.get("name"), str) or not self.ensure["name"]:
            raise ValueError("ensure.name must be a nonempty hook name")

        if self.ensure.get("scope", "global") not in {"global", "module"}:
            raise ValueError("ensure.scope must be 'global' or 'module'")

        if self.ensure.get("position", "append") not in {"append", "prepend"}:
            raise ValueError("ensure.position must be 'append' or 'prepend'")

        if "stage" in self.ensure:
            raise ValueError(
                "ensure.stage is not supported; configure the hook's registered stage"
            )

        if not isinstance(self.ensure.get("args", {}), Mapping):
            raise TypeError("ensure.args must be a mapping")

    def apply(self, config: dict[str, Any]) -> dict[str, Any]:
        global_hooks = config.setdefault("global_hooks", [])
        if global_hooks is None:
            global_hooks = []
            config["global_hooks"] = global_hooks

        if not isinstance(global_hooks, list):
            raise TypeError("global_hooks must be a list")

        # Snapshot matches: inserted hooks must not trigger additional insertion.
        matching = [
            (module, spec)
            for module, spec in _iter_requesters(config)
            if _match(spec, self.when)
        ]
        for module, requester in matching:
            if self.set_defaults:
                if not isinstance(requester, dict):
                    raise TypeError(
                        "set_defaults requires declarative requester hook definitions"
                    )

                args = requester.setdefault("args", {})
                if not isinstance(args, dict):
                    raise TypeError("requester args must be mutable mapping")

                for key, val in self.set_defaults.items():
                    if args.get(key) is None:
                        args[key] = val

            requester_args = _args(requester)
            target_args = dict(self.ensure.get("args") or {})
            for key in self.forward_args:
                if key in requester_args:
                    target_args[key] = requester_args[key]

                elif not isinstance(requester, Mapping) and hasattr(requester, key):
                    target_args[key] = getattr(requester, key)

            scope = self.ensure.get("scope", "global")
            if scope == "global":
                target_hooks = global_hooks
            else:
                if not isinstance(module, dict):
                    raise ValueError(
                        "module scope requires requester in a declarative module"
                    )

                target_hooks = module.setdefault("hooks", [])
                if not isinstance(target_hooks, list):
                    raise TypeError("module hooks must be a list")

            target_name = self.ensure["name"].replace("_", "-")
            target_id = self.ensure.get("id")
            if _contains_target(target_hooks, target_name, target_args, target_id):
                continue

            target = {"name": self.ensure["name"]}
            if target_id is not None:
                target["id"] = target_id

            if target_args:
                target["args"] = target_args

            if self.ensure.get("position", "append") == "prepend":
                target_hooks.insert(0, target)
            else:
                target_hooks.append(target)

        return config

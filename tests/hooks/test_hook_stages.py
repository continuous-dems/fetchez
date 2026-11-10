"""Contract tests for hook-stage normalization and compatibility."""

from dataclasses import dataclass, field

import pytest

from fetchez.core import run_fetchez
from fetchez.hooks.base import FetchHook


STAGES = ("manifest", "file", "stream", "collection", "finalize")


class LegacyHook(FetchHook):
    name = "legacy"
    meta_stage = "file"
    # Intentionally inherits unrestricted meta_stages=None.


class StreamOnlyHook(FetchHook):
    name = "stream-only"
    meta_stage = "stream"
    meta_stages = ("stream",)


class FlexibleHook(FetchHook):
    name = "flexible"
    meta_stage = "manifest"
    meta_stages = ("manifest", "file", "collection", "finalize")


class FinalizeHook(FetchHook):
    name = "finalize-only"
    meta_stage = "finalize"
    meta_stages = ("finalize",)


@pytest.mark.parametrize("stage", STAGES)
def test_legacy_hook_allows_known_stage_overrides(stage):
    """Missing meta_stages must not break existing stage overrides."""
    assert LegacyHook(stage=stage).stage == stage


def test_legacy_hook_uses_default_stage():
    assert LegacyHook().stage == "file"


def test_single_stage_hook_uses_declared_default():
    assert StreamOnlyHook().stage == "stream"
    assert StreamOnlyHook(stage="stream").stage == "stream"


@pytest.mark.parametrize("stage", ("manifest", "file", "collection", "finalize"))
def test_stream_only_hook_rejects_incompatible_override(stage):
    with pytest.raises(ValueError, match="stream-only|stream|support|allow"):
        StreamOnlyHook(stage=stage)


@pytest.mark.parametrize("stage", FlexibleHook.meta_stages)
def test_multi_stage_hook_accepts_supported_stages(stage):
    assert FlexibleHook(stage=stage).stage == stage


def test_multi_stage_hook_rejects_other_known_stage():
    with pytest.raises(ValueError, match="flexible|stream|support|allow"):
        FlexibleHook(stage="stream")


def test_finalize_hook_defaults_to_finalize():
    assert FinalizeHook().stage == "finalize"


@pytest.mark.parametrize(
    ("alias", "expected"),
    (("pre", "manifest"), ("POST", "collection"), ("FiLe", "file")),
)
def test_stage_aliases_and_case_are_normalized(alias, expected):
    assert LegacyHook(stage=alias).stage == expected


def test_allowed_stage_declarations_normalize_aliases():
    class AliasHook(FetchHook):
        name = "alias-hook"
        meta_stage = "pre"
        meta_stages = ("pre", "post")

    assert AliasHook().stage == "manifest"
    assert AliasHook(stage="post").stage == "collection"


@pytest.mark.parametrize("bad_stage", ("bogus", "finalise", "", 123, None))
def test_explicit_unknown_stages_raise_instead_of_falling_back(bad_stage):
    # None is intentionally excluded: None means use the declared default.
    if bad_stage is None:
        assert LegacyHook(stage=None).stage == "file"
    else:
        with pytest.raises((ValueError, TypeError), match="stage|Stage"):
            LegacyHook(stage=bad_stage)


def test_empty_supported_stage_declaration_is_invalid():
    class EmptyStages(FetchHook):
        name = "empty-stages"
        meta_stage = "file"
        meta_stages = ()

    with pytest.raises(ValueError, match="stage|Stage"):
        EmptyStages()


def test_default_must_be_among_supported_stages():
    class MismatchedDefault(FetchHook):
        name = "mismatched-default"
        meta_stage = "file"
        meta_stages = ("stream",)

    with pytest.raises(ValueError, match="default|file|stage"):
        MismatchedDefault()


def test_invalid_stage_in_supported_declaration_is_rejected():
    class InvalidStages(FetchHook):
        name = "invalid-stages"
        meta_stage = "file"
        meta_stages = ("file", "imaginary")

    with pytest.raises(ValueError, match="imaginary|stage"):
        InvalidStages()


@dataclass(eq=False)
class FakeModule:
    name: str = "source"
    results: list = field(default_factory=list)
    hooks: list = field(default_factory=list)
    fetch_calls: int = 0
    discover_calls: int = 0

    def fetch_entry(self, entry, check_size=True, verbose=True):
        self.fetch_calls += 1
        return 0

    def run(self):
        self.discover_calls += 1
        return self


@pytest.fixture(autouse=True)
def no_hook_history(monkeypatch):
    import fetchez.core as core

    monkeypatch.setattr(core.utils, "_log_hook_history", lambda *a, **kw: None)


def _module(hooks=()):
    return FakeModule(
        results=[{"url": "file:///dummy.bin", "dst_fn": "dummy.bin"}],
        hooks=list(hooks),
    )


@pytest.mark.parametrize("ignore_failures", (False, True))
@pytest.mark.parametrize("scope", ("module", "global"))
def test_runtime_rejects_mutated_incompatible_stage_before_fetch(
    scope, ignore_failures
):
    hook = StreamOnlyHook()
    hook.stage = "finalize"  # Python callers can mutate a prebuilt instance.
    module = _module([hook] if scope == "module" else [])
    global_hooks = [hook] if scope == "global" else []

    with pytest.raises((ValueError, TypeError), match="stage|Stage|support|allow"):
        run_fetchez(
            [module],
            threads=1,
            global_hooks=global_hooks,
            ignore_failures=ignore_failures,
            discover=True,
        )

    assert module.discover_calls == 0
    assert module.fetch_calls == 0


def test_runtime_rejects_mutated_unknown_stage_before_fetch():
    hook = LegacyHook()
    hook.stage = "invalid-stage"
    module = _module([hook])

    with pytest.raises((ValueError, TypeError), match="stage|Stage"):
        run_fetchez([module], threads=1)

    assert module.fetch_calls == 0


def test_runtime_allows_compatible_prebuilt_hook_override():
    hook = FlexibleHook()
    hook.stage = "finalize"
    module = _module([hook])

    result = run_fetchez([module], threads=1)

    assert len(result) == 1
    assert module.fetch_calls == 1


def test_invalid_global_hook_fails_before_any_module_fetches():
    hook = FinalizeHook()
    hook.stage = "stream"
    modules = [_module(), _module()]

    with pytest.raises((ValueError, TypeError), match="stage|Stage|support|allow"):
        run_fetchez(modules, threads=1, global_hooks=[hook])

    assert all(m.fetch_calls == 0 for m in modules)

"""A strict recipe must not silently skip failed hook or module initialization."""

from __future__ import annotations

import pytest

from fetchez.recipe import Recipe


@pytest.mark.parametrize("failed_stage", ["global_hooks", "modules"])
@pytest.mark.parametrize("ignore_failures", [False, True])
def test_recipe_init_error_honors_ignore_failures(
    monkeypatch, tmp_path, failed_stage, ignore_failures
):
    recipe = Recipe(
        {
            "project": {"name": "strict-test"},
            "region": [0, 1, 0, 1],
            "modules": [{"module": "tnm", "args": {"products": "1_3as"}}],
            "global_hooks": [],
        }
    )
    monkeypatch.setattr(recipe, "_check_integrity", lambda: None)
    monkeypatch.setattr(recipe, "_expand_hooks", lambda values: values)
    monkeypatch.setattr(recipe, "_expand_modules", lambda values: values)
    monkeypatch.setattr(recipe, "_init_modifiers", lambda values: [])
    monkeypatch.setattr(recipe, "_init_schemas", lambda values: [])

    def failed(*args, **kwargs):
        raise RuntimeError(f"injected {failed_stage} initialization failure")

    if failed_stage == "global_hooks":
        monkeypatch.setattr(recipe, "_init_hooks", failed)
    else:
        monkeypatch.setattr(recipe, "_init_hooks", lambda values: [])
        monkeypatch.setattr(recipe, "_init_modules", failed)

    run = recipe.run(outdir=tmp_path, ignore_failures=ignore_failures)
    if ignore_failures:
        assert list(run) == []
    else:
        with pytest.raises(RuntimeError, match="injected .* initialization failure"):
            list(run)

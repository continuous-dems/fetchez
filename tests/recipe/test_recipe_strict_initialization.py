"""Initialization errors must honor Recipe.run(ignore_failures=...)."""

from __future__ import annotations

from pathlib import Path

import pytest

from fetchez.recipe import Recipe


@pytest.mark.parametrize("failed_stage", ["global_hooks", "modules"])
@pytest.mark.parametrize("ignore_failures", [False, True])
def test_recipe_init_error_honors_ignore_failures(
    monkeypatch, tmp_path, failed_stage, ignore_failures
):
    """Strict runs propagate initialization failures; tolerant runs skip the batch."""
    recipe = Recipe.from_dict(
        {
            "project": {"name": "strict-test"},
            "region": [0, 1, 0, 1],
            "modules": [{"module": "tnm", "args": {"products": "1_3as"}}],
            "global_hooks": [],
        }
    )

    # The refactored Recipe.compile() passes context via keyword arguments.
    # Keep these fakes compatible with the new signatures, without bypassing
    # compile() itself or its initialization/error handling.
    monkeypatch.setattr(recipe, "_check_integrity", lambda: None)
    monkeypatch.setattr(recipe, "_expand_hooks", lambda values, **kwargs: values)
    monkeypatch.setattr(recipe, "_expand_modules", lambda values, **kwargs: values)
    monkeypatch.setattr(recipe, "_init_modifiers", lambda values, **kwargs: [])
    monkeypatch.setattr(recipe, "_validate_config", lambda config: {})

    def failed(*args, **kwargs):
        raise RuntimeError(f"injected {failed_stage} initialization failure")

    if failed_stage == "global_hooks":
        monkeypatch.setattr(recipe, "_init_hooks", failed)
    else:
        monkeypatch.setattr(recipe, "_init_hooks", lambda values, **kwargs: [])
        monkeypatch.setattr(recipe, "_init_modules", failed)

    # Neither a receipt nor pipeline execution should be attempted on a
    # batch whose component initialization failed.
    monkeypatch.setattr(
        recipe,
        "to_markdown",
        lambda *args, **kwargs: pytest.fail("receipt written for failed batch"),
    )
    monkeypatch.setattr(
        "fetchez.recipe.PipelinePlan.execute",
        lambda self: pytest.fail("executed a failed batch"),
    )

    starting_cwd = Path.cwd()
    run = recipe.run(outdir=tmp_path, ignore_failures=ignore_failures)

    if ignore_failures:
        assert list(run) == []
    else:
        with pytest.raises(
            RuntimeError,
            match=f"injected {failed_stage} initialization failure",
        ):
            list(run)

    assert Path.cwd() == starting_cwd
    assert not (tmp_path / "fetchez_batch_state.json").exists()

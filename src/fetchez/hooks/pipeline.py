"""Execute an embedded Fetchez recipe as a child pipeline.

The hook is deliberately format-agnostic. It forwards optional realized entries,
executes the ordinary recipe engine in an isolated FetchContext, and explicitly
promotes selected child artifacts to the parent catalog.
"""

from dataclasses import replace
from pathlib import Path
import re

from fetchez.hooks import FetchHook
from fetchez.core import PipelineExecutionError
from fetchez.recipe import Recipe, RecipeContext
from fetchez.spatial import Region, yield_parsed_regions


class Pipeline(FetchHook):
    """Run an embedded recipe and optionally publish its output artifacts.

    Parameters
    ----------
    recipe : dict
        A complete embedded Fetchez recipe dictionary.
    inputs : bool
        Pass current (module, entry) pairs as already-acquired child inputs.
        Forwarded entries start at the child's file stage, not manifest.
    publish : dict[str, str]
        Mapping of ``parent_artifact_name: child_artifact_name``. Promotion
        registers artifact records; it does not move output files.
    context : dict, optional
        Overrides for RecipeContext. Relative tile_dir/outdir/shared_cache are
        resolved against the parent's tile_dir (or outdir, then cwd).
        Other fields: region, region_srs, name, batch_name, refresh.
    """

    name = "pipeline"
    meta_stage = "collection"
    meta_category = "workflow"
    meta_desc = "Execute an embedded child recipe and optionally publish its artifacts."
    meta_effects = ["publishes-artifacts"]

    def __init__(self, recipe, inputs=False, publish=None, context=None, **kwargs):
        super().__init__(**kwargs)
        if not isinstance(recipe, dict):
            raise TypeError("pipeline.recipe must be an embedded recipe mapping")
        if not isinstance(inputs, bool):
            raise TypeError("pipeline.inputs must be a boolean")
        if publish is not None and not isinstance(publish, dict):
            raise TypeError("pipeline.publish must be a mapping")
        if context is not None and not isinstance(context, dict):
            raise TypeError("pipeline.context must be a mapping")
        allowed = {
            "region",
            "region_srs",
            "name",
            "batch_name",
            "outdir",
            "tile_dir",
            "shared_cache",
            "refresh",
        }
        unknown = set(context or {}) - allowed
        if unknown:
            raise ValueError(f"Unsupported pipeline context keys: {sorted(unknown)}")
        self.recipe_config = recipe
        self.include_inputs = inputs
        self.publish = dict(publish or {})
        self.context_overrides = dict(context or {})

    @staticmethod
    def _one_region(value, srs):
        if value is None:
            return None
        if isinstance(value, Region):
            region = Region.from_list(value.to_list())
        else:
            regions = list(yield_parsed_regions(value))
            if len(regions) != 1:
                raise ValueError(
                    "Child pipeline region must describe exactly one region"
                )
            region, _ = regions[0]
        region.srs = srs
        return region

    def _recipe_context(self):
        parent = getattr(self.context, "plan", None)
        if parent is None:
            raise RuntimeError("pipeline hook requires an active parent PipelinePlan")

        original = getattr(parent, "recipe_context", None)
        if original is None:
            # Compatible with existing, manually constructed PipelinePlan objects.
            original = RecipeContext(
                region=parent.region,
                region_srs=parent.config.get("region_srs", "EPSG:4326"),
                name=parent.config.get("project", {}).get("name", "fetchez"),
                batch_name=parent.batch_name,
                outdir=parent.tile_dir,
                tile_dir=parent.tile_dir,
                shared_cache=parent.shared_cache,
            )

        child_project = self.recipe_config.get("project") or {}
        child_name = self.context_overrides.get(
            "name", child_project.get("name", "child_pipeline")
        )
        # Use a filesystem-safe subdirectory; callers can override tile_dir.
        subdir = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(child_name)).strip("._")
        subdir = subdir or "child_pipeline"
        base_dir = Path(original.tile_dir or original.outdir or Path.cwd()).resolve()
        child_dir = base_dir / subdir
        child_srs = self.context_overrides.get(
            "region_srs", self.recipe_config.get("region_srs", original.region_srs)
        )
        if "region" in self.context_overrides:
            region_value = self.context_overrides["region"]
        elif self.recipe_config.get("region") is not None:
            region_value = self.recipe_config["region"]
        else:
            region_value = original.region

        def resolve_directory(key, default):
            value = self.context_overrides.get(key, default)
            if value is None:
                return None
            path = Path(value).expanduser()
            return (path if path.is_absolute() else base_dir / path).resolve()

        return replace(
            original,
            name=str(child_name),
            region=self._one_region(region_value, child_srs),
            region_srs=child_srs,
            tile_dir=resolve_directory("tile_dir", child_dir),
            outdir=resolve_directory("outdir", child_dir),
            shared_cache=resolve_directory("shared_cache", original.shared_cache),
            batch_name=self.context_overrides.get("batch_name", original.batch_name),
            refresh=self.context_overrides.get("refresh", original.refresh),
        )

    def run(self, entries):
        if self.context is None:
            raise RuntimeError("pipeline hook requires a bound FetchContext")

        # Detect runaway logical nesting: compiled plan identity alone cannot
        # detect repeated recipe compilation. Limit this initial interface.
        depth = 0
        ancestor = self.context
        while ancestor is not None:
            depth += 1
            ancestor = ancestor.parent
        if depth >= 16:
            raise PipelineExecutionError("Maximum nested pipeline depth (16) exceeded")

        compile_context = self._recipe_context()
        if compile_context.tile_dir is not None:
            compile_context.tile_dir.mkdir(parents=True, exist_ok=True)
        if compile_context.outdir is not None:
            compile_context.outdir.mkdir(parents=True, exist_ok=True)

        child_plan = Recipe.from_dict(self.recipe_config).compile(compile_context)
        result = self.context.execute(
            child_plan,
            inputs=entries if self.include_inputs else None,
        )

        # Resolve everything first: a missing child artifact should not result
        # in publishing a partially successful subset into the parent catalog.
        promotions = []
        for parent_name, child_name in self.publish.items():
            artifact = result.artifacts.get(child_name)
            promotions.append((parent_name, artifact))

        for parent_name, artifact in promotions:
            self.context.artifacts.publish(
                parent_name,
                artifact.path,
                owner=artifact.owner,
                metadata=artifact.metadata,
            )

        # Composition is side-effect-only: never replace parent entries.
        return entries

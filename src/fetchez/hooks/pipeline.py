from fetchez.hooks import FetchHook


class PipelineHook(FetchHook):
    """Execute an independent Fetchez pipeline within the current context."""

    name = "pipeline"
    meta_stage = "collection"
    meta_category = "workflow"

    def __init__(
        self,
        recipe,
        inputs=False,
        publish=None,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.recipe_config = recipe
        self.include_inputs = inputs
        self.publish = publish or {}

    def run(self, entries):
        from fetchez.recipe import Recipe

        child_plan = Recipe.from_dict(self.recipe_config).compile()

        result = self.context.execute(
            child_plan,
            inputs=entries if self.include_inputs else None,
        )

        for parent_name, child_name in self.publish.items():
            artifact = result.artifacts.get(child_name)

            self.context.artifacts.publish(
                parent_name,
                artifact.path,
                metadata=artifact.metadata,
            )

        return entries

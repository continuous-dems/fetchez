# 💡 Feature Requests

Have an idea that could make Fetchez more useful? We'd love to hear it!

Fetchez is developed around real-world geospatial data workflows, and many improvements begin as suggestions from users and contributors. Whether you're looking for support for a new data source, an additional processing hook, or an improvement to an existing workflow, feature requests help guide the project's development.

**You don't need to write code to contribute an idea.**

## Requesting a Feature

Feature requests are managed through [GitHub Issues](https://github.com/continuous-dems/fetchez/issues).

1. **Search existing issues.** Someone may have suggested something similar. Feel free to add your use case or join the discussion.
2. **Open a new issue.** Visit [New Issue](https://github.com/continuous-dems/fetchez/issues/new/choose) and select the appropriate feature request template, if available.
3. **Describe your idea.** Explain what you'd like Fetchez to do and why it would be useful.
4. **Join the discussion.** Maintainers and other contributors may suggest alternatives, request details, or help refine the proposal.

### What Makes a Useful Feature Request?

You don't need a complete technical design. The most helpful requests explain the problem and how the proposed feature would improve an existing workflow.

Consider including:

- **The problem:** What are you trying to accomplish, and what's currently difficult or missing?
- **The proposed behavior:** How would you like Fetchez to support this workflow?
- **An example:** A command, YAML recipe, Python snippet, dataset, or API endpoint that demonstrates the use case.
- **Existing alternatives:** Have you tried an existing module, hook, or workaround?
- **Broader applicability:** Could other Fetchez users benefit from this capability?

For larger changes, it's especially helpful to explain the general problem rather than prescribe a specific implementation.

## New Data Sources and Processing Features

Fetchez is designed to be extensible, so not every new capability requires a change to the core framework.

Before requesting a new provider-specific module, consider whether one of the generic interfaces can already handle the source:

- `local_fs` — Local files and directories
- `http_index` — HTTP directories and downloadable links
- `rest_api` — REST and JSON-based APIs
- `stac` — Spatiotemporal Asset Catalogs
- `thredds` — THREDDS scientific data catalogs

Similarly, existing hooks, YAML bundles, presets, and reader profiles may provide the behavior you're looking for without requiring new Python code.

If an existing component almost works but needs an additional option or capability, that's also a useful feature request!

See [Modules & Bundles](../user_guide/modules_and_bundles.md) and [Hooks & Presets](../user_guide/hooks_and_presets.md) for available options.

## Proposing Architectural Changes

Fetchez aims to remain modular, generic, and extensible. Features that can be useful across multiple data sources or workflows are particularly valuable.

For significant changes to the framework, registries, execution lifecycle, or component interfaces, please open an issue for discussion **before beginning a large implementation**.

This gives contributors an opportunity to discuss compatibility, existing abstractions, and whether the feature belongs in Fetchez core or an extension.

## Want to Implement Your Idea?

Contributions are welcome! If you'd like to work on a feature yourself, mention that in your issue so others know you're interested.

Once the approach has been discussed, see the [Development Setup](dev_setup.md) and [Pull Request Guide](pull_requests.md) to get started.

You can also contribute reusable YAML bundles, hook presets, recipes, documentation, and examples without writing a new Python component.

## Questions or Early Ideas?

Not sure whether something should be a feature request, a bug report, or a new extension?

You're welcome to discuss ideas in our [community Zulip chat](https://cudem.zulip.org/) before opening an issue.

For behavior that appears broken rather than missing, see [Reporting Bugs](bugs.md).

**[Browse existing issues](https://github.com/continuous-dems/fetchez/issues)** or **[propose a feature](https://github.com/continuous-dems/fetchez/issues/new/choose)**.

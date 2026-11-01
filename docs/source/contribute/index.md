# Contributing to Fetchez

Thank you for considering contributing to Fetchez! Whether you're fixing a bug, adding a new data module, improving documentation, or extending the framework with custom components, this guide will help you get started.

Contributions come in many forms — code, configuration, documentation, or community support. You don't need to write Python to make Fetchez better.

## How to Read This Guide

### Building an Extension or Plugin?

If you want to create reusable modules, hooks, or readers:

1. **[Development Setup](dev_setup.md)** — Get your environment ready
2. **[Component Architecture](architecture.md)** — Understand how Fetchez is structured
3. **[Entry Architecture](entry.md)** — Understand Fetchez entries and how they're used
4. **[Developing Modules](modules.md)** — Write custom data source modules
5. **[Creating Hooks](user_hooks.md)** — Implement processing hooks
6. **[Adding Plugins](user_plugins.md)** — Register local or distributed extensions
7. **[Entry Points](entry_points.md)** — Configure package entry points for distribution

### Reporting Issues or Requesting Features?

* **[Report Bugs](bugs.md)** — How to file effective issue reports
* **[Feature Requests](feature_requests.md)** — Proposing new capabilities

### Improving Documentation?

* **[Documentation Guide](docs.md)** — Style, structure, and publishing

### Submitting Code Changes?

* **[Pull Requests](pull_requests.md)** — Contribution workflow and review process
* **[License](license.md)** — Licensing terms for contributors

---

## What We Welcome

**Configuration Contributions** (no code required):
* New YAML bundles for common module combinations
* Hook presets for recurring processing patterns
* Reader profiles for specific data formats
* Example recipes demonstrating real-world workflows

**Code Contributions**:
* Data source modules (provider-specific or generic)
* Processing hooks and stream readers
* Modifiers and schemas for recipe validation
* Bug fixes and performance improvements

**Documentation**:
* Module and hook reference pages
* Usage examples and tutorials
* API documentation
* Contributing to this guide

---

## Quick Links

* **User Guide** — [Learn how to use Fetchez](../user_guide/index.md)
* **API Reference** — [Technical documentation](../api/index.md)
* **Community Chat** — [Ask questions on Zulip](https://cudem.zulip.org/)
* **GitHub Issues** — [Report bugs or propose features](https://github.com/continuous-dems/fetchez/issues)
* **Repository** — [Browse source code](https://github.com/continuous-dems/fetchez)

---

```{toctree}
:maxdepth: 2

dev_setup
architecture
entry
bugs
docs
modules
user_plugins
user_hooks
entry_points
feature_requests
pull_requests
license
```

## Indices and Tables

* {ref}`genindex`
* {ref}`modindex`
* {ref}`search`

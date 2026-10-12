# 📚 Improving Documentation & Examples

Great documentation is just as important as code! We want Fetchez to be accessible to everyone, from students to seasoned geospatial engineers. Contributions of any size are welcome, including improvements to a single component's documentation.

## How you can help

- **Fix typos and improve clarity.** Found a confusing sentence in the README, user guide, or a docstring? Please fix it! Small changes make a big difference.
- **Add examples.** Have a useful workflow, such as fetching and gridding lidar data with PDAL or automating bathymetry updates? Share a Jupyter Notebook, Markdown tutorial, or shell script in `examples/` through a pull request.
- **Improve module documentation.** Clarify module help text, registered metadata, and class docstrings. Where relevant, describe datasets, resolution, coordinate reference systems, vertical datums, and configuration options.
- **Improve hook documentation.** Update hook docstrings and `meta_*` declarations to explain their purpose, effects, expected stream representations, dependencies, and useful combinations with other hooks.
- **Write component reference pages.** Add a dedicated user-guide page for an undocumented module, hook, reader, profile, or another registered component.

## Documenting individual components

Fetchez is built around dynamically registered modules, hooks, readers, profiles, data types, presets, and other components. The registries and CLI make them discoverable, but a dedicated documentation page can explain *when and why* to use a component, not just what arguments it accepts.

We have an **ongoing GitHub issue for individual component documentation**. It is intended to remain open as documentation coverage grows, and documentation PRs can reference it without closing it. You do not need to understand the entire Fetchez architecture to contribute: documenting one component, or a small related group, is valuable.

### Where documentation belongs

Place detailed pages under the appropriate section of `docs/user_guide/`, for example:

```text
docs/user_guide/
├── hooks/
│   ├── index.md
│   ├── remote_archive_footprint.md
│   └── remote_raster_footprint.md
├── modules/
├── readers/
├── profiles/
├── streams/
└── datatypes/
```

These are illustrative locations; use the existing documentation structure and create new reference directories only when appropriate. Keep introductory pages such as `hooks_and_presets.md`, `modules_and_bundles.md`, and `streams.md` focused on concepts and navigation, with links to detailed references.

Simple components may be documented together; complex ones may warrant their own pages. Documentation is also welcome for bundles, reusable workflows, recipe modifiers, and schemas.

### What to include

A useful component page generally covers:

1. **Overview:** What the component does and when it is useful.
2. **Usage:** A practical CLI, Python API, or YAML recipe example, as appropriate.
3. **Configuration:** Important arguments, defaults, and options.
4. **Inputs and outputs:** Relevant entry metadata, artifact data types, stream types, or generated files.
5. **Dependencies and limitations:** Required packages, companion hooks, assumptions, and known restrictions.
6. **Related components:** Links to useful modules, hooks, readers, profiles, or presets.

Include only the sections relevant to the component. A short, accurate page with a working example is better than a long page of generic descriptions.

### How to contribute a reference page

1. Choose a component using the Fetchez CLI (for example, `fetchez hooks list` or `fetchez modules list`) or its registry.
2. Check whether a documentation page already exists; improvements to existing pages are welcome too.
3. Add or update its Markdown page in the appropriate `docs/user_guide/` location.
4. Include at least one useful, reproducible example when practical.
5. Link the page from the relevant index or documentation navigation.
6. Open a pull request referencing the ongoing documentation issue (for example, `Refs #ISSUE_NUMBER`).

Feel free to comment on the issue to coordinate work or ask questions. It is a continuing contribution opportunity, not a checklist that must be completed in one PR.

### Documentation guidelines

- Use the component's actual registered name and currently supported arguments.
- Prefer publicly available datasets or small local files in examples.
- Distinguish built-in Fetchez behavior from capabilities provided by extensions such as Globato.
- Describe relevant hook metadata (`meta_stage`, `meta_effects`, `meta_accepts`, `meta_produces`, `meta_requires`, etc.) where it helps users understand the component. Do not imply that descriptive metadata automatically enforces compatibility or inserts dependencies.
- Explain whether an operation changes the primary entry artifact (`dst_fn`), creates new entries, or generates supplementary artifacts, when relevant.
- Avoid presenting proposed or experimental behavior as an existing feature.
- Keep the top-level user guide approachable and place component-specific details in the reference pages.

Documentation, examples, docstrings, and registry metadata complement each other. Improving any one of them makes Fetchez easier to use and extend.

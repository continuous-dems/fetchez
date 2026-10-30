# 💻 Command Line Interface

The `fetchez` command line tool allows you to chain modules and hooks together.

The `build` command composes registered Modules, Bundles, Hooks, and Presets
into a Fetchez Recipe. Components are chained from left to right and may be
executed immediately or exported as reusable YAML.

```{eval-rst}
.. click:: fetchez.cli:cli
   :nested: full
   :prog: fetchez
```

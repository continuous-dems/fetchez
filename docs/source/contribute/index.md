# Contributing to Fetchez

Thank you for considering contributing to Fetchez! We welcome contributions from the community to help make geospatial data acquisition easier for everyone.

Whether you're fixing a bug, adding a new data module, or improving documentation, this guide will help you get started.

## 🛠️Development Setup

1.  **Fork the Repository:** Click the "Fork" button on the top right of the GitHub page.
2.  **Clone your Fork:**
    ```bash
    git clone https://github.com/YOUR_USERNAME/fetchez.git
    cd fetchez
    ```
3.  **Create a Virtual Environment:**
    ```bash
    python -m venv venv
    source venv/bin/activate  # On Windows: venv\Scripts\activate
    ```
4.  **Install in Editable Mode:**
    ```bash
    pip install -e .
    ```

## 🐛 Reporting Bugs

If you find a bug, please create a new issue on GitHub. Include:
* The exact command you ran.
* The error message / traceback.
* Your operating system and Python version.

## 📚 Improving Documentation & Examples

Great documentation is just as important as code! We want Fetchez to be accessible to everyone, from students to seasoned geospatial engineers.

**How you can help:**
* **Fix Typos & Clarity:** Found a confusing sentence in the README or a typo in a docstring? Please fix it! Small changes make a big difference.
* **Add Examples:** Have a cool workflow? (e.g. *"Fetching and gridding lidar data with PDAL"* or *"Automating bathymetry updates"*). Share it!
    * Create a Jupyter Notebook, a Markdown tutorial, or a simple shell script.
    * Submit it to the `examples/` directory via a Pull Request.
* **Improve Module Docs:** Many modules could use better descriptions or more usage examples in their help text.
    * Update the `help_text` in the module's `@cli.cli_opts` decorator.
    * Update the class docstring with specific details about the dataset (resolution, vertical datum, etc.).

***Best Practices for Sharing***

If you have developed a robust workflow (e.g., "Standard Archival Prep" or "Cloud Optimized GeoTIFF Conversion", or whatever), you can share it easily!

* Test your preset: Ensure the hooks run in the correct order (e.g., unzip before filter).

* Add a Help String: The "help" field in the JSON is displayed in the CLI when users run `fetchez --help`. Make it descriptive if you can!

* Share the YAML: You can post your YAML snippet in a GitHub Issue or Discussion or on our Zulip chat.

* Contribute to Core: If a preset is universally useful, you can propose adding it to the `init_presets()` function in `fetchez/presets.py` via a Pull Request.

***Module-Specific Overrides***

You can use the modules section to create specialized shortcuts for specific datasets.

For example, you often use fetchez dav (NOAA Digital Coast) but only want to check if data exists without downloading gigabytes of lidar. Now, you can create a preset that filters for "footprint" files only by writing a series of hooks and then combining them into a preset. Then, when you run `fetchez dav --help`, you will see your custom `--footprint-only` flag listed under "DAV Presets", but it won't clutter the menu for other modules.



## 📝 Pull Request Guidelines

1.  **Branching:** Create a new branch for your changes (`git checkout -b feature/add-mydata`).
2.  **Coding Style:**
    * Follow PEP 8 guidelines.
    * Use type hints where possible.
    * Use `fetchez.spatial` helpers for region parsing; avoid manual coordinate unpacking.
    * Use `logging` instead of `print`.
3.  **Documentation:** Update the docstrings in your code. If you added a new module, ensure it has a class-level docstring describing the data source.
4.  **Commit Messages:** Write clear, concise commit messages (e.g., "Add support for MyData API").
5.  **Pull Request:** Make a pull request to merge your branch into main.

## ⚖ License

* **Core Contributions:** By contributing to this repository (including new modules in fetchez/modules/), you agree that your contributions will be licensed under the project's MIT License. You retain your individual copyright to your work, but you grant the project a perpetual, non-exclusive right to distribute it under the MIT terms.

* **External Plugins:** If you develop a module as an external user plugin (e.g., loaded from ~/.fetchez/plugins/ and not merged into this repository), you are free to license it however you wish.


```{toctree}
:maxdepth: 2

modules
user_plugins
user_hooks
```
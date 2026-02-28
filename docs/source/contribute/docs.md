# 📚 Improving Documentation & Examples

Great documentation is just as important as code! We want Fetchez to be accessible to everyone, from students to seasoned geospatial engineers.

**How you can help:**
* **Fix Typos & Clarity:** Found a confusing sentence in the README or a typo in a docstring? Please fix it! Small changes make a big difference.
* **Add Examples:** Have a cool workflow? (e.g. *"Fetching and gridding lidar data with PDAL"* or *"Automating bathymetry updates"*). Share it!
    * Create a Jupyter Notebook, a Markdown tutorial, or a simple shell script.
    * Submit it to the `examples/` directory via a Pull Request.
* **Improve Module Docs:** Many modules could use better descriptions or more usage examples in their help text.
    * Update the `help_text` in the module's `@cli.cli_opts` decorator.
    * Update the class docstring with specific details about the dataset (resolution, vertical datum, etc.).

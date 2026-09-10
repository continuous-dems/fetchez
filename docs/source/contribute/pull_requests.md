# 📝 Pull Request Guidelines

1.  **Branching:** Create a new branch for your changes (`git checkout -b feature/add-mydata`).
2.  **Coding Style:** Refer to our Community Compass policy on [Software Quality](https://continuous-dems-community-compass.readthedocs.io/en/latest/policies/software-quality/).
    * Follow PEP 8 guidelines.
    * Use type hints where possible.
    * Use `fetchez.spatial` helpers for region parsing; avoid manual coordinate unpacking less we lose the attached Region attributes, such as it's SRS.
    * Use `logging` instead of `print`.
3.  **Documentation:** Update the docstrings in your code. If you added a new module, ensure it has a class-level docstring describing the data source and all associated `meta_` tags in it's class definition.
4.  **Architectural Philosophy (Core vs. Extensions):**
    *   **Lightweight Core:** The `fetchez` core repository acts strictly as a lightweight orchestrator. Standard data modules submitted to core should generally just "scan an API and return endpoints where possible."
    *   **Heavy Extensions:** If your new module requires heavy, domain-specific logic (e.g., executing complex Shapely footprint intersections, requiring unique local file cross-referencing, or needing custom CLI flags that only apply to one provider), it should be built as a plugin or submitted directly to an extension package (like `globato`), not to `fetchez` core.
		> *Note: Extensions can host their own FetchModules just like they host hooks!*
5.  **Commit Messages:** Write clear, concise commit messages (e.g., "Add support for MyData API").
6.  **Pull Request:** Make a pull request to merge your branch into main.

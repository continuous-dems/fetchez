# 📝 Pull Request Guidelines

1.  **Branching:** Create a new branch for your changes (`git checkout -b feature/add-mydata`).
2.  **Coding Style:** Refer to our Community Compass policy on [Software Quality](https://continuous-dems-community-compass.readthedocs.io/en/latest/policies/software-quality/).
    * Follow PEP 8 guidelines.
    * Use type hints where possible.
    * Use `fetchez.spatial` helpers for region parsing; avoid manual coordinate unpacking less we lose the attached Region attributes, such as it's SRS.
    * Use `logging` instead of `print`.
3.  **Documentation:** Update the docstrings in your code. If you added a new module, ensure it has a class-level docstring describing the data source and all associated `meta_` tags in it's class definition.
5.  **Commit Messages:** Write clear, concise commit messages (e.g., "Add support for MyData API").
6.  **Pull Request:** Make a pull request to merge your branch into main.

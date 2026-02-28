# 📝 Pull Request Guidelines

1.  **Branching:** Create a new branch for your changes (`git checkout -b feature/add-mydata`).
2.  **Coding Style:** Refer to our Team Compass policy on [Software Quality](https://continuous-dems-team-compass.readthedocs.io/policies/software-quality/).
    * Follow PEP 8 guidelines.
    * Use type hints where possible.
    * Use `fetchez.spatial` helpers for region parsing; avoid manual coordinate unpacking.
    * Use `logging` instead of `print`.
3.  **Documentation:** Update the docstrings in your code. If you added a new module, ensure it has a class-level docstring describing the data source.
4.  **Commit Messages:** Write clear, concise commit messages (e.g., "Add support for MyData API").
5.  **Pull Request:** Make a pull request to merge your branch into main.

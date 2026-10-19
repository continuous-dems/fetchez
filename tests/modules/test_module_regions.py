# test_module_regions.py

import os
import ast
import pytest

from pathlib import Path

MODULES_DIR = Path(__file__).parent / ".." / "src" / "fetchez" / "modules"


def get_module_files():
    """Yields all python files in the modules directory except base.py."""

    for root, _, files in os.walk(MODULES_DIR):
        for file in files:
            if file.endswith(".py") and file not in ["base.py", "__init__.py"]:
                yield os.path.join(root, file)


class RegionAttributeChecker(ast.NodeVisitor):
    """Visits nodes in the AST to detect `self.region` usage."""

    def __init__(self):
        self.violations = []

    def visit_Attribute(self, node):
        if node.attr == "region":
            if isinstance(node.value, ast.Name) and node.value.id == "self":
                self.violations.append(node.lineno)
        self.generic_visit(node)


@pytest.mark.parametrize("filepath", get_module_files())
def test_modules_use_wgs_region(filepath):
    """Enforces that fetch modules use `self.wgs_region` instead of `self.region`.
    API queries must be in WGS84, and downstream native spatial logic belongs in hooks.
    """

    with open(filepath, "r", encoding="utf-8") as f:
        source_code = f.read()

    tree = ast.parse(source_code, filename=filepath)

    # Visit the nodes to check for self.region
    checker = RegionAttributeChecker()
    checker.visit(tree)

    # Format error message if violations are found
    if checker.violations:
        filename = os.path.basename(filepath)
        lines = ", ".join(map(str, checker.violations))
        pytest.fail(
            f"Architecture Violation in {filename}: Found 'self.region' on line(s) {lines}. "
            f"Fetch modules must use 'self.wgs_region' for API queries. "
            f"Native spatial logic should be deferred to hooks."
        )

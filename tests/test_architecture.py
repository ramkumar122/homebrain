"""The domain must stay pure: no I/O frameworks, no cloud SDKs.

This is what lets the in-memory to AWS swap be a substitution, not a rewrite.
"""

import ast
from pathlib import Path

import pytest

DOMAIN = Path(__file__).resolve().parents[1] / "src" / "homebrain" / "domain"
FORBIDDEN = {"boto3", "botocore", "fastapi", "starlette", "mcp", "httpx", "uvicorn", "requests"}


def _imported_roots(source: str) -> set[str]:
    roots: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            roots.add(node.module.split(".")[0])
    return roots


@pytest.mark.parametrize("path", sorted(DOMAIN.rglob("*.py")), ids=lambda p: p.name)
def test_domain_module_has_no_forbidden_imports(path: Path):
    bad = _imported_roots(path.read_text()) & FORBIDDEN
    assert not bad, f"{path.relative_to(DOMAIN.parent)} imports {sorted(bad)}"


def test_checker_catches_forbidden_imports():
    assert _imported_roots("import boto3\nfrom mcp.types import Tool\n") == {"boto3", "mcp"}

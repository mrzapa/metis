"""CI guard -- prevent raw ``urlopen`` regressions.

After M17 Phase 3b, every outbound HTTP call in ``metis_app/`` routes
through :func:`metis_app.network_audit.client.audited_urlopen`. This
test fails if anyone adds a new raw ``urllib.request.urlopen`` (or the
equivalent ``request.urlopen`` after ``from urllib import request``)
outside the audit module itself.

The guard uses AST walking (not a regex / string search) so it is not
fooled by ``urlopen`` appearing inside a docstring, a comment, or a
string literal -- only real call sites count.

Add a file to :data:`ALLOWLIST` only with an ADR justification. The
audit wrapper ``client.py`` is the sole allowed caller today; that is
the single seam the whole audit panel relies on.
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
METIS_APP = REPO_ROOT / "metis_app"

# Only these paths are allowed to call ``urlopen`` directly. Everything
# else must route through :func:`audited_urlopen`. Additions REQUIRE an
# ADR entry explaining why the audit indirection cannot apply.
ALLOWLIST: frozenset[Path] = frozenset(
    {
        METIS_APP / "network_audit" / "client.py",
    }
)


def _iter_python_files(root: Path) -> list[Path]:
    """Yield every ``.py`` file under ``root``, skipping ``__pycache__``."""
    return [p for p in root.rglob("*.py") if "__pycache__" not in p.parts]


def _file_calls_raw_urlopen(path: Path) -> list[tuple[int, str]]:
    """Return every (lineno, rendered call) where ``urlopen`` is invoked.

    Matches both ``urllib.request.urlopen(...)`` and the dotted-access
    form ``request.urlopen(...)`` reached via ``from urllib import
    request``. Bare ``urlopen(...)`` is also caught if someone imports
    the name directly -- unusual but worth defending against.
    """
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(path))
    offenders: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        # Attribute-style calls: X.urlopen(...)
        if isinstance(func, ast.Attribute) and func.attr == "urlopen":
            offenders.append((node.lineno, ast.unparse(func)))
            continue
        # Bare urlopen(...) from ``from urllib.request import urlopen``
        if isinstance(func, ast.Name) and func.id == "urlopen":
            offenders.append((node.lineno, ast.unparse(func)))
    return offenders


def test_no_raw_urlopen_outside_network_audit() -> None:
    """Fail if any file outside ``ALLOWLIST`` calls a raw ``urlopen``."""
    offenders: list[str] = []
    for py in _iter_python_files(METIS_APP):
        if py in ALLOWLIST:
            continue
        for line, snippet in _file_calls_raw_urlopen(py):
            offenders.append(f"{py.relative_to(REPO_ROOT)}:{line} -> {snippet}")
    assert not offenders, (
        "Raw urlopen call detected outside metis_app/network_audit/client.py. "
        "Use audited_urlopen with trigger_feature + user_initiated kwargs; see "
        "plans/network-audit/plan.md Phase 3. Offenders:\n  "
        + "\n  ".join(offenders)
    )

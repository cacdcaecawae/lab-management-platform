"""Module dependency rules (.agents/notes/implemented/architecture/2026-11-17-module-boundaries.md, docs/architecture.md).

Backend: an app may import only the apps listed for it below, and never another app's views / urls / admin.
Frontend: a page (in src/modules/<module>/ or the not yet moved src/views/) may import another module's `api`
only; shared code may not import src/modules/ at all (the router may import each module's index).
Tests, migrations and conftest.py are not checked: fixtures build data across modules.
Usage: python scripts/check_module_deps.py   (exit 1 and one line per violation)
"""

import ast
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BASE = {"projects", "accounts", "core"}
BUSINESS = {"datasets", "procurement", "meetings", "achievements", "specimens", "equipment", "inventory", "research",
            "knowledge", "reports"}
ALLOWED = {
    "core": set(),
    "accounts": {"core"},
    "projects": {"accounts", "core"},
    "datasets": BASE,
    "procurement": BASE,
    "meetings": BASE,
    "achievements": BASE,
    "specimens": BASE,
    "equipment": BASE | {"procurement"},
    "inventory": BASE | {"procurement"},
    "research": BASE | {"datasets", "equipment", "specimens"},
    "knowledge": BASE | {"equipment"},
    "reports": BASE | {"datasets", "research"},
    "workbench": BASE | BUSINESS,
    "system": {"accounts", "core"},
}
PRIVATE = re.compile(r"^(views|urls|admin)$|_(views|urls)$")


def skipped(rel):
    parts = rel.split("/")
    return "migrations" in parts or "tests" in parts or parts[-1] == "conftest.py" or parts[-1].startswith("test_")


def backend_violations(app, rel, source):
    found = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            # `from reports import views` names the submodule only in the alias
            names = [f"{node.module}.{a.name}" for a in node.names]
        elif isinstance(node, ast.Import):
            names = [a.name for a in node.names]
        else:
            continue
        for name in names:
            top, *rest = name.split(".")
            if top not in ALLOWED or top == app:
                continue
            if top not in ALLOWED[app]:
                found.append(f"{rel}:{node.lineno} {app} → {top}（分层表里没有这条依赖）")
            elif rest and PRIVATE.search(rest[0]):
                found.append(f"{rel}:{node.lineno} {app} → {top}.{rest[0]}（{rest[0]} 是模块内部）")
    return list(dict.fromkeys(found))  # `from x import a, b` breaking the layer table is one violation


IMPORT = re.compile(r"""(?:from|import)\s*\(?\s*['"]([^'"]+)['"]""")


def frontend_violations(rel, source):
    """rel: path from frontend/src, e.g. modules/equipment/views/EquipmentDetailView.vue"""
    parts = rel.split("/")
    # Pages still in src/views/ (not moved into a module yet) are pages too: they may use a module's api.
    own = parts[1] if parts[0] == "modules" else "views" if parts[0] == "views" else None
    found = []
    for lineno, line in enumerate(source.splitlines(), 1):
        for target in IMPORT.findall(line):
            if target.startswith("@/"):
                path = target[2:]
            elif target.startswith("."):
                path = os.path.normpath(os.path.join(os.path.dirname(rel), target)).replace(os.sep, "/")
            else:
                continue
            tparts = path.split("/")
            if tparts[0] != "modules" or len(tparts) < 2 or tparts[1] == own:
                continue
            if own is None:
                if not (parts[0] == "router" and len(tparts) == 2):
                    found.append(f"{rel}:{lineno} 公共代码 → {target}（公共部分不能引用模块）")
            elif tparts[2:3] != ["api"]:
                found.append(f"{rel}:{lineno} {own} → {target}（只能引用别的模块的 api）")
    return found


def main():
    found = []
    backend = ROOT / "backend"
    for app in ALLOWED:
        for path in sorted((backend / app).rglob("*.py")):
            rel = path.relative_to(ROOT).as_posix()
            if not skipped(rel):
                found += backend_violations(app, rel, path.read_text(encoding="utf-8"))
    src = ROOT / "frontend" / "src"
    for path in sorted(src.rglob("*")):
        if path.suffix in {".ts", ".vue"} and not path.name.endswith(".test.ts"):
            found += frontend_violations(path.relative_to(src).as_posix(), path.read_text(encoding="utf-8"))
    for line in found:
        print(line)
    print(f"module dependencies: {len(found)} violation(s)" if found else "module dependencies: ok")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())

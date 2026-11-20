"""Compare the simple PostgreSQL settings invariant without importing Django settings."""
import argparse
import ast
from pathlib import Path
import subprocess
import sys


SETTINGS = "backend/config/settings.py"
ENV_GET = ast.dump(ast.parse("os.environ.get", mode="eval").body)
MARKERS = {"DATABASES", "DATABASE_ROUTERS", "ATOMIC_REQUESTS", "isolation_level",
           "CONN_MAX_AGE", "DISABLE_SERVER_SIDE_CURSORS"}


def value_supported(node):
    if isinstance(node, ast.Constant):
        return isinstance(node.value, (str, bool, int, type(None)))
    if isinstance(node, ast.Dict):
        return all(isinstance(key, ast.Constant) and isinstance(key.value, str)
                   and value_supported(value) for key, value in zip(node.keys, node.values))
    if isinstance(node, ast.BoolOp) and isinstance(node.op, ast.Or):
        return all(value_supported(value) for value in node.values)
    if isinstance(node, ast.Call):
        return (
            ast.dump(node.func) == ENV_GET
            and not node.keywords and 1 <= len(node.args) <= 2
            and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str)
            and all(isinstance(arg, ast.Constant) for arg in node.args)
        )
    return False


def signature(source):
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        raise ValueError("settings.py could not be parsed") from exc
    definitions = [
        statement for statement in tree.body
        if isinstance(statement, ast.Assign) and len(statement.targets) == 1
        and isinstance(statement.targets[0], ast.Name) and statement.targets[0].id == "DATABASES"
    ]
    if len(definitions) != 1:
        raise ValueError("expected one unconditional DATABASES assignment")
    database = definitions[0]
    if not isinstance(database.value, ast.Dict) or not value_supported(database.value):
        raise ValueError("unsupported DATABASES expression; review manually")

    overrides = []
    environment = []
    for statement in tree.body:
        if statement is database:
            continue
        nodes = list(ast.walk(statement))
        parents = {child: node for node in nodes for child in ast.iter_child_nodes(node)}
        for node in nodes:
            if isinstance(node, ast.ImportFrom) and any(alias.name == "*" for alias in node.names):
                raise ValueError("wildcard settings import; review manually")
            if (isinstance(node, ast.ImportFrom) and node.module == "os") or (
                isinstance(node, ast.Import)
                and any(alias.name == "os" and alias.asname for alias in node.names)
            ):
                raise ValueError("indirect os binding; review database environment manually")
            if isinstance(node, ast.Name) and node.id == "os" and isinstance(node.ctx, ast.Load):
                if not isinstance(parents.get(node), ast.Attribute):
                    raise ValueError("indirect os use; review database environment manually")
            if isinstance(node, ast.Attribute) and node.attr == "environ":
                parent = parents.get(node)
                if isinstance(parent, ast.Attribute):
                    call = parents.get(parent)
                    if isinstance(call, ast.Call) and call.func is parent:
                        continue
                if isinstance(parent, ast.Subscript) and parent.value is node:
                    continue
                raise ValueError("indirect environment use; review database environment manually")
            if isinstance(node, ast.Name) and node.id == "DATABASES":
                raise ValueError("DATABASES referenced outside its assignment; review manually")
        if any((isinstance(node, ast.Name) and node.id in MARKERS)
               or (isinstance(node, ast.Attribute) and node.attr in MARKERS)
               or (isinstance(node, ast.Constant) and isinstance(node.value, str) and node.value in MARKERS)
               or (isinstance(node, ast.alias) and ({node.name, node.asname} & MARKERS))
               for node in nodes):
            overrides.append(ast.dump(statement))
        # The dictionary's only callable dependency is os.environ.get. Keep its setup in scope.
        if any((isinstance(node, ast.Attribute) and node.attr == "environ")
               or (isinstance(node, ast.Name) and node.id == "os")
               or (isinstance(node, ast.alias) and (node.name == "os" or node.asname == "os"))
               for node in nodes):
            neutral_read = (
                isinstance(statement, ast.Assign)
                and all(isinstance(target, ast.Name) and target.id != "os" for target in statement.targets)
                and value_supported(statement.value)
            )
            if not neutral_read:
                environment.append(ast.dump(statement))
    return ast.dump(database.value), overrides, environment


def check(repo, sync):
    def read_ref(ref):
        return subprocess.check_output(["git", "-C", str(repo), "show", f"{ref}:{SETTINGS}"],
                                       text=True, encoding="utf-8")

    try:
        baseline_source = read_ref(sync)
    except (OSError, subprocess.CalledProcessError, UnicodeError):
        print(f"{SETTINGS}: cannot read SYNC baseline {sync}; fetch its history before reviewing")
        return 1
    try:
        baseline = signature(baseline_source)
    except ValueError as exc:
        print(f"{SETTINGS}: unsupported SYNC baseline: {exc}")
        return 2
    changed = False
    for label, read in (("HEAD", lambda: read_ref("HEAD")),
                        ("index", lambda: read_ref("")),
                        ("worktree", lambda: (repo / SETTINGS).read_text(encoding="utf-8"))):
        try:
            if signature(read()) != baseline:
                print(f"{SETTINGS} ({label}): DATABASES or related settings changed since {sync}")
                changed = True
        except (OSError, subprocess.CalledProcessError, UnicodeError, ValueError) as exc:
            print(f"{SETTINGS} ({label}): cannot establish unchanged database settings ({exc})")
            changed = True
    return 2 if changed else 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("repo", type=Path)
    parser.add_argument("sync")
    args = parser.parse_args()
    sys.exit(check(args.repo, args.sync))

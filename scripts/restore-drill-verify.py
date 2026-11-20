"""Run inside the matching backend image; never starts the application server."""
import hashlib
import json
import os
import random
import re
import sys

sys.path.insert(0, "/app")
os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings"

FILE_PATTERNS = {
    "DataFile": re.compile(r"datasets/[0-9]+/[a-f0-9]{32}"),
    "DocVersion": re.compile(r"knowledge/[a-f0-9]{32}(?:\.[^/\\\x00-\x1f]{1,15})?"),
}


def check_metadata(kind, path, expected):
    if not FILE_PATTERNS[kind].fullmatch(path) or not re.fullmatch(r"[a-f0-9]{64}", expected):
        raise ValueError(f"{kind}: unsupported backup file path or checksum")


def select_snapshot(entries):
    if len(entries) != 1:
        raise ValueError("expected exactly one backup snapshot")
    snapshot = entries[0]
    if snapshot["hostname"] != "lab" or not re.fullmatch(r"[a-f0-9]{64}", snapshot["id"]):
        raise ValueError("invalid lab backup snapshot")
    return snapshot


def check_applied_migrations(applied, disk_migrations):
    known = set(disk_migrations)
    for migration in disk_migrations.values():
        known.update(migration.replaces)
    if set(applied) - known:
        raise ValueError("backup has applied migrations that this backend image does not know")


def sample(limit, seed):
    import django
    django.setup()
    from django.apps import apps
    from django.core.management import call_command
    from django.db import connection
    from django.db.migrations.loader import MigrationLoader
    from django.db.migrations.recorder import MigrationRecorder

    # migrate --check catches pending image migrations; also reject dumps newer than the image.
    loader = MigrationLoader(connection)
    check_applied_migrations(MigrationRecorder(connection).applied_migrations(), loader.disk_migrations)
    call_command("migrate", check=True, interactive=False, verbosity=0, stdout=sys.stderr)
    model = apps.get_model
    labels = [("accounts", "User"), ("projects", "Project"), ("research", "Experiment"),
              ("datasets", "DataFile"), ("procurement", "PurchaseRequest"), ("knowledge", "DocVersion")]
    counts = {name: model(app, name)._base_manager.count() for app, name in labels}
    print("恢复表行数：" + json.dumps(counts), file=sys.stderr)
    latest = model("reports", "WeeklyReport").history.order_by("-history_date").values_list("history_date", flat=True).first()
    print(f"最新周报历史：{latest or '无'}", file=sys.stderr)

    rng = random.Random(seed)
    rows = []
    for app, name in (labels[3], labels[-1]):
        objects = model(app, name)._base_manager
        ids = list(objects.order_by("pk").values_list("pk", flat=True))
        for pk in rng.sample(ids, min(limit, len(ids))):
            path, checksum = objects.filter(pk=pk).values_list("file", "sha256").get()
            check_metadata(name, path, checksum)
            rows.append([name, path, checksum])
    json.dump(rows, sys.stdout)


def main():
    mode = sys.argv[1]
    if mode == "snapshot":
        snapshot = select_snapshot(json.load(sys.stdin))
        print("快照时间：" + snapshot["time"], file=sys.stderr)
        print(snapshot["id"])
    elif mode == "sample":
        sample(int(sys.argv[2]), sys.argv[3])
    elif mode == "includes":
        for name, path, expected in json.load(sys.stdin):
            check_metadata(name, path, expected)
            print(name, "/data/files/" + path, expected, sep="\t")
    elif mode == "verify-file":
        kind, expected = sys.argv[2:]
        if hashlib.file_digest(sys.stdin.buffer, "sha256").hexdigest() != expected:
            raise ValueError(f"{kind}: checksum mismatch")
    else:
        raise ValueError("unknown restore drill mode")


if __name__ == "__main__":
    main()

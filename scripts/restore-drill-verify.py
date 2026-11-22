"""Run inside the matching backend image; never starts the application server."""
import hashlib
import json
import os
import random
import re
import sys

sys.path.insert(0, "/app")
os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings"

# Every stored upload name (core.files.stored_name and the other upload_to functions): a folder, perhaps a numbered
# one, a random hex name, perhaps an extension. Nothing else reaches restic's arguments.
FILE_PATH = re.compile(r"[a-z][a-z0-9-]*/(?:[0-9]+/)?[a-f0-9]{32}(?:\.[^./\\\x00-\x1f]{1,30})?")
# What a file is checked against: its SHA256 column, else its size column, else only that it is in the snapshot.
EXPECTED = re.compile(r"[a-f0-9]{64}|size:[0-9]+|present")


def check_metadata(kind, path, expected):
    if not FILE_PATH.fullmatch(path) or not EXPECTED.fullmatch(expected):
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
    from django.db.models import FileField
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

    # Every kind of upload (data, documents, attachments, photos, full texts, pictures), up to `limit` of each.
    rng = random.Random(seed)
    rows = []
    for upload_model in apps.get_models():
        columns = {f.name for f in upload_model._meta.concrete_fields}
        if "history_id" in columns:  # a history copy names files replaced since
            continue
        for field in upload_model._meta.concrete_fields:
            if not isinstance(field, FileField):
                continue
            kind = f"{upload_model._meta.label}.{field.name}"
            size = next((c for c in ("size", f"{field.name}_size") if c in columns), None)
            objects = upload_model._base_manager.exclude(**{field.name: ""})
            ids = list(objects.order_by("pk").values_list("pk", flat=True))
            for pk in rng.sample(ids, min(limit, len(ids))):
                row = objects.filter(pk=pk).values(field.name, *[c for c in ("sha256", size) if c in columns]).get()
                expected = row.get("sha256") or (f"size:{row[size]}" if size and row[size] is not None else "present")
                check_metadata(kind, row[field.name], expected)
                rows.append([kind, row[field.name], expected])
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
        # A file missing from the snapshot already failed `restic dump` in front of this.
        kind, expected = sys.argv[2:]
        digest, size = hashlib.sha256(), 0
        for chunk in iter(lambda: sys.stdin.buffer.read(1 << 20), b""):
            digest.update(chunk)
            size += len(chunk)
        if expected != "present" and expected not in (digest.hexdigest(), f"size:{size}"):
            raise ValueError(f"{kind}: checksum mismatch")
    else:
        raise ValueError("unknown restore drill mode")


if __name__ == "__main__":
    main()

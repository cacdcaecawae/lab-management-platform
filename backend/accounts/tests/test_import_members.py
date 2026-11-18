import csv
import io

import pytest
from django.core.management import CommandError, call_command

from accounts.models import User

pytestmark = pytest.mark.django_db

HEADER = "username,name,role,email,phone,research_direction\n"


def run(path, *args):
    out, err = io.StringIO(), io.StringIO()
    call_command("import_members", str(path), *args, stdout=out, stderr=err)
    return out.getvalue(), err.getvalue()


def write_csv(tmp_path, body, encoding="utf-8-sig"):
    path = tmp_path / "members.csv"
    path.write_text(HEADER + body, encoding=encoding)
    return path


def test_imports_bom_csv_and_prints_passwords(tmp_path, group):
    path = write_csv(tmp_path, "2026001,张三,,z@example.com,138,导波\n2026002,李四,advisor,,,\n")
    out, err = run(path, "--group", group.name)
    result = list(csv.DictReader(io.StringIO(out)))
    assert [row["username"] for row in result] == ["2026001", "2026002"]
    zhang = User.objects.get(username="2026001")
    assert zhang.group == group and zhang.role == "student" and zhang.name == "张三"
    assert zhang.must_change_password and zhang.check_password(result[0]["password"])
    assert User.objects.get(username="2026002").role == "advisor"
    assert "导入 2 人" in err


def test_skips_existing_duplicate_and_invalid_role(tmp_path, group, student_a):
    path = write_csv(tmp_path, "s_a,已有,,,,\n2026003,甲,,,,\n2026003,甲重复,,,,\n2026004,乙,boss,,,\n")
    out, err = run(path, "--group", group.name)
    assert [row["username"] for row in csv.DictReader(io.StringIO(out))] == ["2026003"]
    assert "第 2 行跳过" in err and "第 4 行跳过" in err and "第 5 行跳过" in err
    assert not User.objects.filter(username="2026004").exists()
    assert User.objects.get(username="s_a").name == "s_a"  # existing user untouched


def test_writes_output_file(tmp_path, group):
    path = write_csv(tmp_path, "2026001,张三,,,,\n", encoding="utf-8")
    result_path = tmp_path / "result.csv"
    out, _ = run(path, "--group", group.name, "--output", str(result_path))
    assert out == ""
    rows = list(csv.DictReader(result_path.open(encoding="utf-8-sig")))
    assert rows[0]["username"] == "2026001"
    assert User.objects.get(username="2026001").check_password(rows[0]["password"])


def test_unwritable_or_existing_output_rolls_back(tmp_path, group):
    path = write_csv(tmp_path, "2026001,张三,,,,\n")
    with pytest.raises(CommandError, match="未导入"):
        run(path, "--group", group.name, "--output", str(tmp_path / "no_such_dir" / "result.csv"))
    existing = tmp_path / "result.csv"
    existing.write_text("username,password\nold,secret\n", encoding="utf-8")
    with pytest.raises(CommandError, match="不会覆盖"):
        run(path, "--group", group.name, "--output", str(existing))
    assert not User.objects.filter(username="2026001").exists()
    assert "old,secret" in existing.read_text(encoding="utf-8")


def test_unknown_group_creates_nothing(tmp_path, db):
    path = write_csv(tmp_path, "2026001,张三,,,,\n")
    with pytest.raises(CommandError, match="课题组不存在"):
        run(path, "--group", "不存在的组")
    assert not User.objects.exists()


def test_rejects_non_utf8_and_missing_column(tmp_path, group):
    path = write_csv(tmp_path, "2026001,张三,,,,\n", encoding="gbk")
    with pytest.raises(CommandError, match="UTF-8"):
        run(path, "--group", group.name)
    path.write_text("name\n张三\n", encoding="utf-8")
    with pytest.raises(CommandError, match="username"):
        run(path, "--group", group.name)

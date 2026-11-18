import csv

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils.crypto import get_random_string

from accounts.models import ResearchGroup, User

COLUMNS = ["username", "name", "role", "email", "phone", "research_direction"]


class Command(BaseCommand):
    help = (
        "从 CSV 导入成员（列：username,name,role,email,phone,research_direction；UTF-8，可带 BOM）。"
        "为每个新用户生成随机初始密码，结果 username,password 输出到 stdout 或 --output。"
    )

    def add_arguments(self, parser):
        parser.add_argument("csv_file")
        parser.add_argument("--group", required=True, help="课题组名称（必须已存在）")
        parser.add_argument("--output", help="把用户名和初始密码写入该 CSV 文件")

    def handle(self, csv_file, group, output, **options):
        try:
            research_group = ResearchGroup.objects.get(name=group)
        except ResearchGroup.DoesNotExist:
            raise CommandError(f"课题组不存在：{group}")
        rows = self.read_rows(csv_file)

        created, skipped = [], 0
        with transaction.atomic():
            for line, row in enumerate(rows, start=2):
                values = {col: (row.get(col) or "").strip() for col in COLUMNS}
                values["role"] = values["role"] or User.Role.STUDENT
                if not values["username"]:
                    skipped += self.skip(line, "username 为空")
                    continue
                if User.objects.filter(username=values["username"]).exists():
                    skipped += self.skip(line, f"用户名 {values['username']} 已存在")
                    continue
                password = get_random_string(12)
                user = User(**values, group=research_group, must_change_password=True)
                user.set_password(password)
                try:
                    user.full_clean()  # rejects an invalid role, email or username format
                except ValidationError as exc:
                    skipped += self.skip(line, f"{values['username']}：{'；'.join(exc.messages)}")
                    continue
                user.save()
                created.append((user.username, password))

            # Written inside the transaction: if the passwords cannot be saved, no accounts are created.
            # Mode "x": overwriting an earlier result file would lose the passwords it holds.
            if output:
                try:
                    with open(output, "x", encoding="utf-8-sig", newline="") as f:
                        self.write_result(f, created)
                except OSError as exc:
                    raise CommandError(f"无法写入结果文件（不会覆盖已有文件），本次未导入任何成员：{exc}")
            else:
                self.write_result(self.stdout, created)

        self.stderr.write(f"导入 {len(created)} 人，跳过 {skipped} 行。")

    def read_rows(self, csv_file):
        try:
            with open(csv_file, encoding="utf-8-sig", newline="") as f:
                reader = csv.DictReader(f)
                if "username" not in (reader.fieldnames or []):
                    raise CommandError(f"缺少 username 列，需要的列：{','.join(COLUMNS)}")
                return list(reader)
        except OSError as exc:
            raise CommandError(f"无法读取文件：{exc}")
        except UnicodeDecodeError:
            raise CommandError("文件不是 UTF-8 编码（Excel 请另存为“CSV UTF-8”）")

    def skip(self, line, reason):
        self.stderr.write(f"第 {line} 行跳过：{reason}")
        return 1

    def write_result(self, f, created):
        writer = csv.writer(f, lineterminator="\n")
        writer.writerow(["username", "password"])
        writer.writerows(created)

"""Base role student / advisor plus the 管理员 and 终审人 tags, and member details (issue #48 R1).

Existing managers become students with the 管理员 tag (they run the group's affairs but no longer see other students'
research records); existing advisors keep reviewing purchases as 终审人. Ops can change either in 系统管理 → 账号."""

import django.contrib.postgres.fields
from django.db import migrations, models


def split_roles(apps, schema_editor):
    User = apps.get_model("accounts", "User")
    User.objects.filter(role="manager").update(role="student", is_manager=True)
    User.objects.filter(role="advisor").update(is_approver=True)


def join_roles(apps, schema_editor):
    User = apps.get_model("accounts", "User")
    User.objects.filter(role="student", is_manager=True).update(role="manager")


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0005_profile_wechat_avatar"),
    ]

    operations = [
        migrations.AddField(
            model_name="user", name="is_manager", field=models.BooleanField(default=False, verbose_name="管理员"),
        ),
        migrations.AddField(
            model_name="user", name="is_approver", field=models.BooleanField(default=False, verbose_name="终审人"),
        ),
        migrations.AddField(
            model_name="user",
            name="identity",
            field=models.CharField(
                blank=True,
                choices=[
                    ("teacher", "教师"), ("postdoc", "博士后"), ("phd", "博士生"), ("master", "硕士生"),
                    ("undergraduate", "本科生"), ("assistant", "科研助理"),
                ],
                max_length=16,
                verbose_name="身份",
            ),
        ),
        migrations.AddField(
            model_name="user",
            name="enrollment_year",
            field=models.PositiveSmallIntegerField(blank=True, null=True, verbose_name="入学年份"),
        ),
        migrations.AddField(
            model_name="user", name="graduated", field=models.BooleanField(default=False, verbose_name="已毕业"),
        ),
        migrations.AddField(
            model_name="user",
            name="tags",
            field=django.contrib.postgres.fields.ArrayField(
                base_field=models.CharField(max_length=20), blank=True, default=list, size=None, verbose_name="词条"
            ),
        ),
        migrations.RunPython(split_roles, join_roles),
        migrations.AlterField(
            model_name="user",
            name="role",
            field=models.CharField(
                choices=[("student", "学生"), ("advisor", "导师")], default="student", max_length=16, verbose_name="基础角色"
            ),
        ),
    ]

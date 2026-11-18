"""Verification seed for verify-lab: scaffolding, not product code. Runs only against the lab_verify database.

Run through launch.sh (manage.py shell). Every account uses PASSWORD below.
"""

from django.conf import settings

from accounts.models import ResearchGroup, User
from projects.models import Project

assert settings.DATABASES["default"]["NAME"] == "lab_verify", "seed.py only runs against lab_verify"

PASSWORD = "Verify-2026!"

group = ResearchGroup.objects.create(name="验证课题组")
other_group = ResearchGroup.objects.create(name="外组")


def make(username, name, grp, role=User.Role.STUDENT, must_change=False):
    return User.objects.create_user(
        username=username, password=PASSWORD, name=name, group=grp, role=role, must_change_password=must_change
    )


s_a = make("s_a", "学生甲", group)
s_b = make("s_b", "学生乙", group)
make("s_new", "新同学", group, must_change=True)
make("mgr", "管理员甲", group, User.Role.MANAGER)
make("adv", "导师甲", group, User.Role.ADVISOR)
make("x_mgr", "外组管理员", other_group, User.Role.MANAGER)
# the ops account: a superuser without a group, which only sees 系统管理
User.objects.create_superuser("ops", password=PASSWORD, name="运维", must_change_password=False)

project = Project.objects.create(group=group, name="导波螺栓松动", leader=s_a, stage="重复性验证")
project.members.set([s_a, s_b])

print(f"seeded {User.objects.count()} users, {Project.objects.count()} project")

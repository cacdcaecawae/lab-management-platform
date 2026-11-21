import smtplib
import socket
import ssl

import pytest

from accounts.models import ResearchGroup, User
from conftest import PASSWORD
from core.models import SiteSettings

pytestmark = pytest.mark.django_db

URLS = ["/api/system/mail/", "/api/system/mail/history/", "/api/system/groups/", "/api/system/accounts/"]
MAIL = {
    "mail_enabled": False, "mail_host": "smtp.example.edu", "mail_port": 465, "mail_security": "ssl",
    "mail_username": "lab@example.edu", "mail_password": "secret-code", "mail_from": "",
}


def test_only_the_ops_account_reaches_system_management(api, ops, student_a, manager, advisor):
    for user in (None, student_a, manager, advisor):
        for url in URLS:
            assert api(user).get(url).status_code == 403, (user, url)
    for url in URLS:
        assert api(ops).get(url).status_code == 200, url
    assert api(ops).get("/api/auth/me/").data["is_superuser"] is True
    # 系统管理 grants no research data: business endpoints still refuse an account without a group
    assert api(ops).get("/api/dashboard/").data["code"] == "no_group"


def test_business_mail_checks_do_not_create_the_settings(api, django_capture_on_commit_callbacks, student_a, manager):
    from procurement.models import Fund

    fund = Fund.objects.create(group=student_a.group, code="F-1", name="经费")
    body = {"fund_id": fund.id, "purpose": "探头", "items": [{"name": "探头", "quantity": 1, "unit_price": "10.00"}]}
    pid = api(student_a).post("/api/purchases/", body, format="json").data["id"]
    with django_capture_on_commit_callbacks(execute=True):
        assert api(student_a).post(f"/api/purchases/{pid}/submit/").status_code == 200
    # mail is off and the settings history will start with the ops account, not this student
    assert not SiteSettings.objects.exists()


def test_ops_must_change_the_initial_password_first(api, ops):
    ops.must_change_password = True
    ops.save()
    assert api(ops).get("/api/system/mail/").data["code"] == "password_change_required"


def test_mail_password_is_never_returned(api, ops):
    r = api(ops).put("/api/system/mail/", MAIL, format="json")
    assert r.status_code == 200 and r.data["password_set"] is True
    assert "mail_password" not in r.data and b"secret-code" not in r.content
    assert b"secret-code" not in api(ops).get("/api/system/mail/").content

    # blank keeps the stored code
    assert api(ops).put("/api/system/mail/", {**MAIL, "mail_password": "", "mail_host": "smtp2.example.edu"}, format="json").status_code == 200
    assert SiteSettings.load().mail_password == "secret-code"

    history = api(ops).get("/api/system/mail/history/")
    assert b"secret-code" not in history.content
    newest = history.data[0]
    assert newest["user"]["name"] == "运维"
    assert {"field": "mail_host", "old": "smtp.example.edu", "new": "smtp2.example.edu"} in newest["changes"]
    assert history.data[1]["reason"] == "修改了授权码"


def test_enabling_mail_needs_a_server_a_sender_and_a_code(api, ops):
    put = lambda body: api(ops).put("/api/system/mail/", {**MAIL, "mail_enabled": True, **body}, format="json")  # noqa: E731
    assert put({"mail_host": ""}).data["errors"] == {"mail_host": ["启用邮件时必须填写 SMTP 服务器"]}
    assert "mail_from" in put({"mail_username": "lab"}).data["errors"]
    assert "mail_password" in put({"mail_password": ""}).data["errors"]
    assert put({"mail_username": "lab", "mail_from": "lab@example.edu"}).status_code == 200
    assert SiteSettings.load().mail_enabled
    # a test mail is sent before mail is switched on, so the sender must make sense then too
    off = {**MAIL, "mail_username": "lab", "mail_from": ""}
    assert "mail_from" in api(ops).put("/api/system/mail/", off, format="json").data["errors"]


def name_mismatch(code):
    exc = ssl.SSLCertVerificationError("certificate verify failed: Hostname / IP address mismatch")
    exc.verify_code = code  # what ssl sets when the certificate names another host (62) or the server is an IP (64)
    return exc


@pytest.mark.parametrize(
    ("exc", "advice"),
    [
        (smtplib.SMTPAuthenticationError(535, b"Error: authentication failed"), "授权码"),
        (smtplib.SMTPSenderRefused(530, b"5.7.0 Must issue a STARTTLS command first", "lab@example.edu"), "先加密"),
        (smtplib.SMTPSenderRefused(553, b"Mail from must equal authorized user", "x@example.edu"), "发件人"),
        (smtplib.SMTPRecipientsRefused({"a@b.cn": (550, b"User not found")}), "收件地址"),
        (smtplib.SMTPDataError(554, b"DT:SPM 163 mx14"), "垃圾邮件"),
        (smtplib.SMTPNotSupportedError("STARTTLS extension not supported by server."), "不支持 STARTTLS"),
        (smtplib.SMTPNotSupportedError("SMTP AUTH extension not supported by server."), "不提供登录"),
        (ssl.SSLCertVerificationError("certificate verify failed: unable to get local issuer certificate"), "不受信任"),
        (name_mismatch(62), "不要填 IP 地址"),
        (name_mismatch(64), "不要填 IP 地址"),
        (ssl.SSLError("[SSL: WRONG_VERSION_NUMBER] wrong version number"), "465 端口选 SSL"),
        (smtplib.SMTPServerDisconnected("Connection unexpectedly closed"), "465 端口选 SSL"),
        (socket.gaierror(11001, "getaddrinfo failed"), "找不到"),
        (ConnectionRefusedError(111, "Connection refused"), "端口"),
        (TimeoutError("timed out"), "超时"),
    ],
)
def test_mail_failures_say_what_to_check(exc, advice):
    from core.mail import describe

    reason, _, said = describe(exc).partition("。")
    assert reason and advice in said
    assert "550 User not found" in describe(smtplib.SMTPRecipientsRefused({"a@b.cn": (550, b"User not found")}))


class RefusingBackend:
    def __init__(self, *args, **kwargs):
        pass

    def send_messages(self, messages):
        raise smtplib.SMTPAuthenticationError(535, b"Error: authentication failed")


def test_test_mail(api, ops, settings, mailoutbox):
    test = lambda: api(ops).post("/api/system/mail/test/", {"to": "ops@example.edu"}, format="json")  # noqa: E731
    assert test().data["code"] == "not_configured"
    api(ops).put("/api/system/mail/", MAIL, format="json")

    # sent with the saved settings even while mail is off, so the account can be tried first
    assert test().data == {"to": "ops@example.edu"}
    assert mailoutbox[0].to == ["ops@example.edu"] and mailoutbox[0].from_email == "lab@example.edu"

    settings.EMAIL_BACKEND = f"{__name__}.RefusingBackend"
    r = test()
    assert r.status_code == 502 and r.data["message"].startswith("发送失败：535 Error: authentication failed。账号或授权码不对")
    shown = api(ops).get("/api/system/mail/").data
    assert shown["last_mail_error"].startswith("535 Error: authentication failed。") and shown["last_mail_error_at"]

    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    assert test().status_code == 200
    assert api(ops).get("/api/system/mail/").data["last_mail_error"] == ""
    assert api(ops).post("/api/system/mail/test/", {"to": "不是邮箱"}, format="json").status_code == 400


def test_notification_failures_show_in_system_management(api, ops, settings, django_capture_on_commit_callbacks, student_a, manager):
    from conftest import enable_mail
    from procurement.models import Fund

    enable_mail()
    settings.EMAIL_BACKEND = f"{__name__}.RefusingBackend"
    manager.email = "mgr@example.edu"
    manager.save()
    fund = Fund.objects.create(group=student_a.group, code="F-1", name="经费")
    body = {"fund_id": fund.id, "purpose": "探头", "items": [{"name": "探头", "quantity": 1, "unit_price": "10.00"}]}
    pid = api(student_a).post("/api/purchases/", body, format="json").data["id"]
    with django_capture_on_commit_callbacks(execute=True):
        assert api(student_a).post(f"/api/purchases/{pid}/submit/").status_code == 200
    assert "535" in api(ops).get("/api/system/mail/").data["last_mail_error"]


def test_groups(api, ops, group, student_a, student_b):
    student_b.is_active = False
    student_b.save()
    listed = api(ops).get("/api/system/groups/").data["results"]
    assert [(g["name"], g["member_count"]) for g in listed] == [("超声检测课题组", 1)]

    r = api(ops).post("/api/system/groups/", {"name": "相控阵课题组", "finance_email": "f@example.edu"}, format="json")
    assert r.status_code == 201 and r.data["member_count"] == 0
    assert api(ops).post("/api/system/groups/", {"name": "相控阵课题组"}, format="json").data["errors"] == {"name": ["已有同名的课题组"]}
    gid = r.data["id"]
    assert api(ops).patch(f"/api/system/groups/{gid}/", {"name": "相控阵成像课题组", "finance_email": ""}, format="json").status_code == 200
    assert ResearchGroup.objects.get(pk=gid).name == "相控阵成像课题组"
    assert api(ops).delete(f"/api/system/groups/{gid}/").status_code == 405


def login(api, username, password):
    return api().post("/api/auth/login/", {"username": username, "password": password}, format="json")


def test_accounts(api, ops, group, other_group, student_a, manager):
    listed = api(ops).get("/api/system/accounts/").data["results"]
    assert {a["username"] for a in listed} == {"s_a", "mgr"}  # the ops account is not listed
    assert api(ops).patch(f"/api/system/accounts/{ops.id}/", {"name": "x"}, format="json").status_code == 404

    body = {"username": "t_adv2", "name": "导师乙", "role": "advisor", "group_id": group.id, "password": "Init-2026-pass!"}
    r = api(ops).post("/api/system/accounts/", body, format="json")
    assert r.status_code == 201 and r.data["group"] == {"id": group.id, "name": group.name} and r.data["must_change_password"]
    assert "password" not in r.data
    assert api(ops).post("/api/system/accounts/", body, format="json").status_code == 409
    assert api(ops).post("/api/system/accounts/", {**body, "username": "t_x", "group_id": 9999}, format="json").status_code == 400
    assert login(api, "t_adv2", "Init-2026-pass!").data["must_change_password"] is True

    advisor_id = r.data["id"]
    assert [a["username"] for a in api(ops).get("/api/system/accounts/", {"role": "advisor"}).data["results"]] == ["t_adv2"]
    assert api(ops).get("/api/system/accounts/", {"group": other_group.id}).data["count"] == 0

    # the group is fixed once created: moving someone changes who can see their records
    api(ops).patch(f"/api/system/accounts/{student_a.id}/", {"role": "manager", "group_id": other_group.id}, format="json")
    student_a.refresh_from_db()
    assert student_a.role == "manager" and student_a.group_id == group.id

    assert api(ops).post(f"/api/system/accounts/{advisor_id}/reset-password/", {"password": "Reset-2026-pass!"}, format="json").status_code == 204
    assert login(api, "t_adv2", "Reset-2026-pass!").status_code == 200
    assert api(ops).patch(f"/api/system/accounts/{advisor_id}/", {"is_active": False}, format="json").status_code == 200
    assert login(api, "t_adv2", "Reset-2026-pass!").status_code in (401, 403)
    assert User.objects.get(pk=advisor_id).check_password("Reset-2026-pass!")
    assert login(api, "mgr", PASSWORD).status_code == 200


def test_ops_corrects_a_login_name(api, ops, student_a, manager):
    url = f"/api/system/accounts/{student_a.id}/"
    r = api(ops).patch(url, {"username": "2026018"}, format="json")
    assert r.status_code == 200 and r.data["username"] == "2026018"
    assert login(api, "2026018", PASSWORD).status_code == 200
    assert api(ops).patch(url, {"username": "mgr"}, format="json").status_code == 409
    assert api(ops).patch(url, {"username": "ops"}, format="json").status_code == 409  # the ops account's name too
    assert api(ops).patch(url, {"username": "有 空格"}, format="json").status_code == 400

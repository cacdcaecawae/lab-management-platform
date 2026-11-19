"""Headless browser pilot. Uses fresh synthetic identities only, never Django's API test client."""
import json
import os
import re
import shutil
import sys
from contextlib import ExitStack
from hashlib import sha256
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import django
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as ec

django.setup()
from accounts.models import User
from django.conf import settings
from django.contrib.sessions.models import Session
from datasets.models import Dataset
from datasets.versions import current_version
from reports.models import WeeklyReport
from research.models import Experiment

APP = "http://127.0.0.1:5273"
EVIDENCE = Path(os.environ["BROWSER_EVIDENCE"])
EXPERIMENT = "合成验证-螺栓预紧力扫描"
REASON = "合成验证-参数表缺少采样率"
REVISION = "合成验证-补充导波幅值重复性数据"
SEED_PASSWORD = "Verify-2026!"


def browser(stack):
    # Explicit binaries: do not permit Selenium Manager to download anything.
    driver = shutil.which("chromedriver")
    if not driver and "CHROMEWEBDRIVER" in os.environ:
        driver = str(Path(os.environ["CHROMEWEBDRIVER"]) / "chromedriver")
    chrome = shutil.which("google-chrome") or shutil.which("chromium")
    if not driver or not Path(driver).is_file() or not chrome:
        raise RuntimeError("Locally installed Chrome and matching ChromeDriver are required")
    opts = webdriver.ChromeOptions()
    opts.binary_location = chrome
    for flag in (
        "--headless=new", "--window-size=1440,1000", "--no-proxy-server",
        "--disable-background-networking", "--disable-component-update", "--disable-sync",
        "--no-first-run", "--disable-default-apps",
        "--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE localhost, EXCLUDE 127.0.0.1",
    ):
        opts.add_argument(flag)
    session = webdriver.Chrome(service=Service(driver), options=opts)
    stack.callback(session.quit)
    session.set_page_load_timeout(20)
    return session


def visit(session, path):
    assert path.startswith("/") and not path.startswith("//")
    session.get(APP + path)


def visible(session, by, value):
    return WebDriverWait(session, 12).until(ec.visibility_of_element_located((by, value)))


def body_has(session, phrase):
    WebDriverWait(session, 12).until(lambda s: phrase in s.find_element(By.TAG_NAME, "body").text)


def button(session, text, within=""):
    selector = f"//button[normalize-space(.)='{text}']"
    if within:
        selector = within + selector
    return WebDriverWait(session, 12).until(ec.element_to_be_clickable((By.XPATH, selector)))


def field_control(session, label, selector):
    # Element Plus puts the label and control inside the same form-item.
    return visible(session, By.XPATH, f"//div[contains(@class,'el-form-item')][./*[contains(@class,'el-form-item__label') and normalize-space(.)='{label}']]//{selector}")


def label_input(session, label, tag="input"):
    return field_control(session, label, tag)


def submit_login(session, who, password):
    visit(session, "/login")
    visible(session, By.CSS_SELECTOR, 'input[autocomplete=username]').send_keys(who)
    visible(session, By.CSS_SELECTOR, 'input[autocomplete=current-password]').send_keys(password)
    button(session, "登录").click()


def login(session, who, password=SEED_PASSWORD):
    submit_login(session, who, password)
    WebDriverWait(session, 12).until(lambda s: urlsplit(s.current_url).path != "/login")


def option(session, label, value):
    # Element Plus hides an empty multiple-select input until its visible wrapper is focused.
    # Click the real wrapper first; do not wait for the hidden combobox or use a JS click.
    field_control(session, label, "div[contains(@class,'el-select__wrapper')]").click()
    combo = field_control(session, label, "input[@role='combobox']")
    listbox = combo.get_attribute("aria-controls")
    assert listbox
    # Options are teleported outside the form, so scope them to this select's listbox.
    visible(session, By.XPATH, f"//*[@id='{listbox}']//*[@role='option'][contains(normalize-space(.),'{value}')]").click()


def screenshot(session, name):
    assert session.current_url.startswith(APP + "/") and "/login" not in session.current_url
    # Include a compact UTF-8 readback even if the runner lacks CJK fonts.
    (EVIDENCE / f"{name}.txt").write_text(session.find_element(By.TAG_NAME, "body").text + "\n", encoding="utf-8")
    if not session.save_screenshot(str(EVIDENCE / f"{name}.png")):
        raise RuntimeError(f"Could not save {name}")


def evidence(name, payload):
    (EVIDENCE / f"{name}.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def record_path(session, section):
    WebDriverWait(session, 12).until(lambda s: re.search(rf"/{section}/\d+$", s.current_url))
    return session.current_url.removeprefix(APP)


def experiments(stack):
    student = browser(stack)
    login(student, "s_a")
    # Create and first-upload through the UI, not an ORM fixture. ORM is read-only evidence.
    visit(student, "/datasets")
    button(student, "新建数据集").click()
    option(student, "项目", "导波螺栓松动")
    label_input(student, "名称").send_keys("验证-导波波形")
    button(student, "创建").click()
    dataset_path = record_path(student, "datasets")
    dataset = Dataset.objects.get(pk=int(dataset_path.rsplit("/", 1)[1]), owner__username="s_a")
    assert dataset.name == "验证-导波波形" and not dataset.files.exists()
    payload = EVIDENCE.parent / "wave_001.csv"
    data = b"t,amp\n0,0\n1,1\n"
    payload.write_bytes(data)
    button(student, "上传文件")
    WebDriverWait(student, 12).until(ec.presence_of_element_located((By.CSS_SELECTOR, "input[type=file]"))).send_keys(str(payload))
    body_has(student, "已上传 1 个文件")
    WebDriverWait(student, 12).until(lambda _: dataset.files.filter(name="wave_001.csv").exists())
    first = dataset.files.get(name="wave_001.csv")
    assert first.size == len(data) and first.sha256 == sha256(data).hexdigest()
    with first.file.open("rb") as saved:
        assert saved.read() == data
    screenshot(student, "experiments-dataset-first-upload")
    visit(student, "/experiments")
    button(student, "新建实验记录").click()
    option(student, "项目", "导波螺栓松动")
    label_input(student, "实验名称").send_keys(EXPERIMENT)
    option(student, "关联数据集（只能选择自己的数据集）", dataset.name)
    button(student, "保存草稿").click()
    body_has(student, "草稿已保存")
    detail = record_path(student, "experiments")
    record = Experiment.objects.get(title=EXPERIMENT, owner__username="s_a")
    assert record.status == "draft" and record.datasets.get().pk == dataset.pk
    screenshot(student, "experiments-draft")

    button(student, "提交").click()
    body_has(student, "记录已锁定；如需修改，请联系导师退回。")
    assert not label_input(student, "实验名称").is_enabled()
    assert not student.find_elements(By.XPATH, "//button[normalize-space(.)='保存草稿' or normalize-space(.)='提交']")
    record.refresh_from_db()
    pinned = record.data_versions[str(dataset.pk)]
    assert record.status == "submitted" and pinned == current_version(dataset)
    assert list(dataset.snapshots.get(digest=pinned).files.values_list("name", flat=True)) == ["wave_001.csv"]
    screenshot(student, "experiments-submit")

    # Append through the ordinary browser file chooser, then open the experiment again.
    payload = EVIDENCE.parent / "wave_002.csv"
    payload.write_text("t,amp\n0,0\n1,2\n", encoding="utf-8")
    visit(student, f"/datasets/{dataset.pk}")
    button(student, "上传文件")
    WebDriverWait(student, 12).until(ec.presence_of_element_located((By.CSS_SELECTOR, "input[type=file]"))).send_keys(str(payload))
    body_has(student, "wave_002.csv")
    WebDriverWait(student, 12).until(lambda _: dataset.files.filter(name="wave_002.csv").exists())
    visit(student, detail)
    body_has(student, "提交后有新增")
    body_has(student, pinned[:12])
    record.refresh_from_db()
    assert record.data_versions == {str(dataset.pk): pinned} and current_version(dataset) != pinned
    screenshot(student, "experiments-pin")

    advisor = browser(stack)
    login(advisor, "adv")
    visit(advisor, "/experiments")
    visible(advisor, By.PARTIAL_LINK_TEXT, record.code).click()
    button(advisor, "退回").click()
    visible(advisor, By.CSS_SELECTOR, '.el-message-box textarea[placeholder="退回原因（必填）"]').send_keys(REASON)
    visible(advisor, By.CSS_SELECTOR, ".el-message-box__btns .el-button--primary").click()
    body_has(advisor, "已退回")
    record.refresh_from_db()
    assert record.status == "draft" and not record.data_versions
    screenshot(advisor, "experiments-return")
    button(advisor, "修改历史").click()
    body_has(advisor, REASON)
    historical = list(record.history.order_by("history_date", "history_id").values_list("status", "history_change_reason"))
    assert any(status == "submitted" for status, _ in historical)
    assert ("draft", REASON) in historical
    screenshot(advisor, "experiments-history")
    visit(student, detail)
    button(student, "保存草稿")
    button(student, "提交")

    peer = browser(stack)
    login(peer, "s_b")
    visit(peer, detail)
    body_has(peer, "记录不存在或无权查看")
    screenshot(peer, "experiments-isolation")
    evidence("experiments-db", {"pinned": pinned, "current": current_version(dataset),
                                 "return_status": record.status, "history": historical})


def fill_report(student):
    for field in ("本周目标", "完成工作", "主要发现与证据", "下周计划"):
        label_input(student, field, "textarea").send_keys(f"合成验证：{field}")


def reports(stack):
    student = browser(stack)
    login(student, "s_a")
    visit(student, "/reports")
    button(student, "写本周周报").click()
    fill_report(student)
    button(student, "保存").click()
    body_has(student, "已保存")
    detail = record_path(student, "reports")
    report = WeeklyReport.objects.get(owner__username="s_a")
    assert report.status == "draft"
    screenshot(student, "reports-write")

    button(student, "提交").click()
    body_has(student, "周报已提交")
    report.refresh_from_db()
    assert report.status == "submitted"
    screenshot(student, "reports-submit")

    advisor = browser(stack)
    login(advisor, "adv")
    visit(advisor, "/reports")
    assert not advisor.find_elements(By.XPATH, "//button[normalize-space(.)='写本周周报']")
    visible(advisor, By.CSS_SELECTOR, f'a[href="{detail}"]').click()
    visible(advisor, By.XPATH, "//label[contains(@class,'el-radio')][normalize-space(.)='需补充']").click()
    visible(advisor, By.CSS_SELECTOR, 'textarea[placeholder="写明需要补充什么（必填）"]').send_keys(REVISION)
    button(advisor, "提交反馈").click()
    body_has(advisor, "反馈已提交")

    visit(student, detail)
    body_has(student, "导师要求补充（导师甲）")
    report.refresh_from_db()
    assert report.status == "needs_revision"
    screenshot(student, "reports-revision")
    label_input(student, "完成工作", "textarea").send_keys("，已补充合成证据")
    button(student, "修改后重新提交").click()
    body_has(student, "周报已提交")
    report.refresh_from_db()
    assert report.status == "submitted" and "已补充合成证据" in report.done
    screenshot(student, "reports-resubmit")

    advisor.refresh()
    visible(advisor, By.XPATH, "//label[contains(@class,'el-radio')][normalize-space(.)='已阅']").click()
    button(advisor, "提交反馈").click()
    body_has(advisor, "反馈已提交")
    report.refresh_from_db()
    feedback = dict(report.feedback.values_list("verdict", "content"))
    assert report.status == "reviewed" and feedback == {"needs_revision": REVISION, "reviewed": ""}
    assert report.feedback.count() == 2 and report.history.count() > 1
    screenshot(advisor, "reports-reviewed")

    visit(student, "/reports/new?week_start=" + str(report.week_start))
    fill_report(student)
    button(student, "保存").click()
    body_has(student, "这一周的周报已经存在")
    screenshot(student, "reports-duplicate-week")
    assert WeeklyReport.objects.filter(owner__username="s_a").count() == 1
    evidence("reports-db", {"status": report.status, "feedback": feedback, "history": report.history.count()})


def wait_path(session, path):
    WebDriverWait(session, 12).until(lambda browser: urlsplit(browser.current_url).path == path)


def evidence_text(session, name):
    # Capture only visible text, not form values, passwords, source or cookies.
    assert session.current_url.startswith(APP + "/")
    text = session.find_element(By.TAG_NAME, "body").text
    (EVIDENCE / f"{name}.txt").write_text(text + "\n", encoding="utf-8")


def login_logout(stack):
    student = browser(stack)
    login(student, "s_a")
    wait_path(student, "/")
    body_has(student, "学生甲（验证课题组）")
    cookie = student.get_cookie(settings.SESSION_COOKIE_NAME)
    assert cookie and Session.objects.filter(session_key=cookie["value"]).exists()
    screenshot(student, "login-ok")

    wrong = browser(stack)
    submit_login(wrong, "s_b", "wrong-password")
    body_has(wrong, "用户名或密码错误")
    assert urlsplit(wrong.current_url).path == "/login"
    assert wrong.get_cookie(settings.SESSION_COOKIE_NAME) is None
    evidence_text(wrong, "login-wrong")

    first = browser(stack)
    login(first, "s_new")
    wait_path(first, "/password")
    body_has(first, "首次登录，请先修改初始密码。")
    screenshot(first, "login-first-restricted")
    visit(first, "/datasets")
    wait_path(first, "/password")
    new_password = "Verify-2026-new!"
    for label, value in (("原密码", SEED_PASSWORD), ("新密码", new_password), ("确认新密码", new_password)):
        label_input(first, label).send_keys(value)
    button(first, "确认修改").click()
    wait_path(first, "/")
    body_has(first, "新同学（验证课题组）")
    user = User.objects.get(username="s_new")
    assert not user.must_change_password and user.check_password(new_password)
    assert not user.check_password(SEED_PASSWORD)
    screenshot(first, "login-first-change")

    visible(student, By.CSS_SELECTOR, ".topbar .user").click()
    visible(student, By.XPATH, "//*[@role='menuitem'][normalize-space(.)='退出登录']").click()
    wait_path(student, "/login")
    assert student.get_cookie(settings.SESSION_COOKIE_NAME) is None
    assert not Session.objects.filter(session_key=cookie["value"]).exists()
    visit(student, "/datasets")
    WebDriverWait(student, 12).until(lambda b: urlsplit(b.current_url).path == "/login"
                                  and parse_qs(urlsplit(b.current_url).query).get("next") == ["/datasets"])
    evidence_text(student, "login-logout")
    evidence("login-db", {"initial_password_replaced": True, "must_change_password": False, "logged_out_session_removed": True})


def members(stack):
    manager = browser(stack)
    login(manager, "mgr")
    visit(manager, "/members")
    button(manager, "新建成员").click()
    # Role is no longer a picker. Assert the fixed value and that editing is not offered.
    role = field_control(manager, "角色", "div[contains(@class,'el-form-item__content')]")
    assert role.text == "学生"
    assert not role.find_elements(By.CSS_SELECTOR, "select, [role=combobox], [role=radio]")
    screenshot(manager, "members-role-limit")
    initial = "Init-2026-pass!"
    label_input(manager, "学号 / 工号（登录名）").send_keys("verify_new_student_01")
    label_input(manager, "姓名").send_keys("合成验证学生丙")
    label_input(manager, "初始密码").send_keys(initial)
    button(manager, "保存").click()
    body_has(manager, "合成验证学生丙")
    user = User.objects.get(username="verify_new_student_01")
    assert user.role == User.Role.STUDENT and user.group.name == "验证课题组"
    assert user.check_password(initial) and user.must_change_password
    screenshot(manager, "members-create")

    table = "//div[contains(@class,'el-table')]"
    advisor = visible(manager, By.XPATH, table + "//tr[td[normalize-space(.)='导师甲']]")
    assert "由运维管理" in advisor.text
    assert not advisor.find_elements(By.XPATH, ".//button[normalize-space(.)='编辑' or normalize-space(.)='重置密码']")
    screenshot(manager, "members-no-edit-supervisors")

    row_path = table + "//tr[td[normalize-space(.)='合成验证学生丙']]"
    button(manager, "编辑", within=row_path).click()
    static_role = field_control(manager, "角色", "div[contains(@class,'el-form-item__content')]")
    assert static_role.text == "学生"
    assert not static_role.find_elements(By.CSS_SELECTOR, "select, [role=combobox], [role=radio]")
    button(manager, "取消").click()
    with ExitStack() as initial_stack:
        initial_student = browser(initial_stack)
        login(initial_student, user.username, initial)
        wait_path(initial_student, "/password")
        body_has(initial_student, "首次登录，请先修改初始密码。")
    button(manager, "重置密码", within=row_path).click()
    reset = "Reset-2026-pass!"
    label_input(manager, "新密码").send_keys(reset)
    button(manager, "重置").click()
    body_has(manager, "密码已重置，该成员下次登录时需修改密码")
    user.refresh_from_db()
    assert user.must_change_password and user.check_password(reset) and not user.check_password(initial)
    peer_new = browser(stack)
    login(peer_new, user.username, reset)
    wait_path(peer_new, "/password")
    body_has(peer_new, "首次登录，请先修改初始密码。")
    screenshot(peer_new, "members-reset")

    peer = browser(stack)
    login(peer, "s_b")
    visit(peer, "/members")
    visible(peer, By.XPATH, row_path)
    search = visible(peer, By.CSS_SELECTOR, 'input[placeholder="搜索姓名、研究方向"]')
    assert not peer.find_elements(By.XPATH, "//th[contains(normalize-space(.),'学号 / 工号')]")
    assert not peer.find_elements(By.XPATH, "//button[normalize-space(.)='新建成员' or normalize-space(.)='重置密码']")
    screenshot(peer, "members-student-view")
    search.send_keys(user.username, Keys.TAB)
    visible(peer, By.CSS_SELECTOR, ".el-table__empty-text")
    assert not peer.find_elements(By.XPATH, row_path)
    screenshot(peer, "members-no-username-search")
    evidence("members-db", {"role": user.role, "group": user.group.name, "initial_password_replaced": True, "must_change_password": True})


if __name__ == "__main__":
    assert settings.DATABASES["default"]["NAME"] == "lab_verify"
    assert settings.DATABASES["default"]["HOST"] == "127.0.0.1"
    ui = sys.modules[__name__]
    sys.modules.setdefault("scenarios", ui)
    from processing import processing
    from responsive import responsive
    from specimen_filters import check_specimen_filters
    import phase4

    scenario = sys.argv[1]
    ordinary = {
        "experiments": experiments, "reports": reports, "login": login_logout,
        "members": members, "processing": processing,
    }
    phase_four = {"meetings": phase4.meetings, "achievements": phase4.achievements, "knowledge": phase4.knowledge}
    with ExitStack() as stack:
        if scenario in ordinary:
            ordinary[scenario](stack)
        elif scenario in phase_four:
            phase_four[scenario](ui, stack)
        elif scenario == "responsive":
            responsive(stack, ui)
        elif scenario == "specimen_filters":
            check_specimen_filters(
                stack, browser=browser, login=login, visit=visit, visible=visible, button=button,
                label_input=label_input, body_has=body_has, record_path=record_path,
                screenshot=screenshot, evidence=evidence,
            )
        else:
            raise SystemExit("Unknown synthetic browser scenario")

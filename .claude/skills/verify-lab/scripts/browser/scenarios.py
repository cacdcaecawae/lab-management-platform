"""Headless browser pilot. Uses fresh synthetic identities only, never Django's API test client."""
import json
import os
import re
import shutil
import sys
from contextlib import ExitStack
from hashlib import sha256
from pathlib import Path

import django
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as ec

django.setup()
from accounts.models import User
from datasets.models import DataFile, Dataset
from datasets.versions import current_version
from django.core.files.base import ContentFile
from projects.models import Project
from reports.models import WeeklyReport
from research.models import Experiment

APP = "http://127.0.0.1:5273"
EVIDENCE = Path(os.environ["BROWSER_EVIDENCE"])
EXPERIMENT = "合成验证-螺栓预紧力扫描"
REASON = "合成验证-参数表缺少采样率"
REVISION = "合成验证-补充导波幅值重复性数据"


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
    return visible(session, By.XPATH, f"//div[contains(@class,'el-form-item')][./label[normalize-space(.)='{label}']]//{selector}")


def label_input(session, label, tag="input"):
    return field_control(session, label, tag)


def login(session, who):
    visit(session, "/login")
    visible(session, By.CSS_SELECTOR, 'input[autocomplete=username]').send_keys(who)
    visible(session, By.CSS_SELECTOR, 'input[autocomplete=current-password]').send_keys("Verify-2026!")
    button(session, "登录").click()
    WebDriverWait(session, 12).until(lambda s: "/login" not in s.current_url)


def option(session, label, value):
    combo = field_control(session, label, "input[@role='combobox']")
    listbox = combo.get_attribute("aria-controls")
    assert listbox
    # The display placeholder is a span, and options are teleported outside the form.
    combo.click()
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


def new_experiment_fixture():
    owner = User.objects.get(username="s_a")
    proj = Project.objects.get(leader=owner)
    data = b"t,amp\n0,0\n1,1\n"
    dataset = Dataset.objects.create(owner=owner, project=proj, name="验证-导波波形")
    DataFile.objects.create(dataset=dataset, name="wave_001.csv", size=len(data),
                            file=ContentFile(data, "wave_001.csv"), sha256=sha256(data).hexdigest(), uploaded_by=owner)
    return dataset


def experiments(stack):
    dataset = new_experiment_fixture()
    student = browser(stack)
    login(student, "s_a")
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


if __name__ == "__main__":
    assert django.conf.settings.DATABASES["default"]["NAME"] == "lab_verify"
    assert django.conf.settings.DATABASES["default"]["HOST"] == "127.0.0.1"
    with ExitStack() as stack:
        {"experiments": experiments, "reports": reports}[sys.argv[1]](stack)

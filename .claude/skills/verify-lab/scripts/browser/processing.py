"""Complete processing-run UI scenario; imports the pilot's synthetic browser helpers.

Run only via the same isolated harness as scenarios.py. ORM use below is read-only.
No script is executed and the synthetic git URL is stored as text, never fetched.
"""
from hashlib import sha256

from selenium.webdriver.common.keys import Keys

from scenarios import (
    APP, EVIDENCE, By, WebDriverWait, ec, browser, login, visit, button,
    option, field_control, label_input, visible, body_has, record_path, screenshot, evidence, files_input,
)
from datasets.versions import current_version
from research.models import Experiment, ProcessingRun


TITLE = "合成验证-完整处理记录"
REASON = "合成验证-请补充处理结论"


def upload(session, panel, dataset, name, data):
    """Through the files panel's own chooser; the stored bytes are checked."""
    path = EVIDENCE.parent / name
    path.write_bytes(data)
    files_input(session, panel).send_keys(str(path))
    body_has(session, "已上传 1 个文件")
    WebDriverWait(session, 12).until(lambda _: dataset.files.filter(name=name).exists())
    row = dataset.files.get(name=name)
    assert row.sha256 == sha256(data).hexdigest() and row.size == len(data)
    with row.file.open("rb") as stored:
        assert stored.read() == data


def submitted_experiment(session, title, filename, data):
    """实验与原始数据 with one raw file, submitted in the seeded project."""
    visit(session, "/experiments")
    button(session, "新建实验与原始数据").click()
    option(session, "项目", "导波螺栓松动")
    label_input(session, "实验名称").send_keys(title)
    button(session, "保存草稿").click()
    body_has(session, "草稿已保存")
    path = record_path(session, "experiments")
    experiment = Experiment.objects.get(pk=int(path.rsplit("/", 1)[1]), owner__username="s_a")
    upload(session, 1, experiment.dataset, filename, data)
    button(session, "提交").click()
    body_has(session, "记录已锁定；如需修改，请联系导师退回。")
    screenshot(session, "processing-input-submitted")
    return experiment


def processing(stack):
    student = browser(stack)
    login(student, "s_a")
    raw = submitted_experiment(student, "合成处理-输入", "processing-input.csv", b"t,amp\n0,1\n")

    visit(student, "/runs")
    button(student, "新建数据处理").click()
    option(student, "项目", "导波螺栓松动")
    label_input(student, "任务名称").send_keys(TITLE)
    # An incomplete draft must remain a draft when submit validation fails.
    button(student, "提交").click()
    body_has(student, "至少引用 1 条原始数据")
    body_has(student, "请上传结果文件或填写结论")
    detail = record_path(student, "runs")
    run = ProcessingRun.objects.get(title=TITLE, owner__username="s_a")
    assert run.status == "draft" and not run.data_versions and run.submitted_at is None
    screenshot(student, "processing-incomplete-rejected")

    option(student, "引用的原始数据", raw.title)
    # Multiple-select stays open after choosing and overlaps the next fields.
    # Dismiss it with the same keyboard interaction a user can perform, not a JS click.
    combo = field_control(student, "引用的原始数据", "input[@role='combobox']")
    listbox = combo.get_attribute("aria-controls")
    assert listbox
    combo.send_keys(Keys.ESCAPE)
    WebDriverWait(student, 12).until(ec.invisibility_of_element_located((By.ID, listbox)))
    upload(student, 1, run.script_dataset, "processing.py", b"# synthetic fixture, never executed\n")
    label_input(student, "方法版本").send_keys("synthetic-v1")
    label_input(student, "运行环境").send_keys("Python 3.12 synthetic-only")
    button(student, "添加参数").click()
    visible(student, By.CSS_SELECTOR, 'input[aria-label="参数名"]').send_keys("window")
    visible(student, By.CSS_SELECTOR, 'input[aria-label="值"]').send_keys("16")
    upload(student, 2, run.output_dataset, "processing-output.csv", b"mean\n1\n")
    label_input(student, "结论", "textarea").send_keys("合成数据处理完成，仅验证记录流程")
    button(student, "保存草稿").click()
    body_has(student, "草稿已保存")
    run.refresh_from_db()
    assert run.status == "draft" and run.experiments.get().pk == raw.pk
    assert run.params == {"window": "16"} and run.environment == "Python 3.12 synthetic-only"
    assert run.method_version == "synthetic-v1" and not run.script_repo
    screenshot(student, "processing-complete-draft")

    button(student, "提交").click()
    body_has(student, "记录已锁定；如需修改，请联系导师退回。")
    run.refresh_from_db()
    pinned = {str(d.pk): current_version(d) for d in (raw.dataset, run.script_dataset, run.output_dataset)}
    assert run.status == "submitted" and run.submitted_at and run.data_versions == pinned
    assert not label_input(student, "任务名称").is_enabled()
    assert not student.find_elements(By.XPATH, "//button[normalize-space(.)='保存草稿' or normalize-space(.)='提交']")
    screenshot(student, "processing-submitted")

    # More raw data after the submit: the run keeps its version and says the cited data changed since.
    visit(student, f"/experiments/{raw.pk}")
    upload(student, 1, raw.dataset, "processing-input-2.csv", b"t,amp\n1,2\n")
    visit(student, detail)
    body_has(student, "提交后有新增")
    run.refresh_from_db()
    assert run.data_versions == pinned and current_version(raw.dataset) != pinned[str(raw.dataset_id)]
    screenshot(student, "processing-pinned")

    advisor = browser(stack)
    login(advisor, "adv")
    visit(advisor, detail)
    button(advisor, "退回").click()
    visible(advisor, By.CSS_SELECTOR, '.el-message-box textarea[placeholder="退回原因（必填）"]').send_keys(REASON)
    visible(advisor, By.CSS_SELECTOR, ".el-message-box__btns .el-button--primary").click()
    body_has(advisor, "已退回")
    run.refresh_from_db()
    assert run.status == "draft" and not run.data_versions
    button(advisor, "修改历史").click()
    body_has(advisor, REASON)
    assert run.history.filter(history_change_reason=REASON, status="draft").exists()
    screenshot(advisor, "processing-return-history")

    # Add git metadata for the second valid submission; no remote URL is visited.
    visit(student, detail)
    visible(student, By.CSS_SELECTOR, 'input[placeholder="仓库地址"]').send_keys("https://example.invalid/synthetic-processing.git")
    visible(student, By.CSS_SELECTOR, 'input[placeholder="commit"]').send_keys("a" * 40)
    visible(student, By.CSS_SELECTOR, 'input[placeholder="入口脚本，如 src/run.py"]').send_keys("src/process.py")
    label_input(student, "结论", "textarea").send_keys("；已补充处理结论")
    button(student, "提交").click()
    body_has(student, "记录已锁定；如需修改，请联系导师退回。")
    run.refresh_from_db()
    final_versions = {str(d.pk): current_version(d) for d in (raw.dataset, run.script_dataset, run.output_dataset)}
    assert run.status == "submitted" and run.data_versions == final_versions
    assert run.script_commit == "a" * 40 and run.script_path == "src/process.py" and "已补充处理结论" in run.conclusion
    assert ProcessingRun.objects.filter(title=TITLE, owner__username="s_a").count() == 1
    screenshot(student, "processing-git-resubmitted")

    # The run names the project and is submitted: classmates in the project read it, the other group does not.
    peer = browser(stack)
    login(peer, "s_b")
    visit(peer, detail)
    body_has(peer, "记录已锁定。")
    screenshot(peer, "processing-shared-s_b")
    outsider = browser(stack)
    login(outsider, "x_mgr")
    visit(outsider, detail)
    body_has(outsider, "记录不存在或无权查看")
    screenshot(outsider, "processing-isolation-x_mgr")
    evidence("processing-db", {"id": run.pk, "status": run.status, "first_pinned": pinned,
                              "final_pinned": final_versions, "script_commit": run.script_commit,
                              "params": run.params, "history_count": run.history.count()})

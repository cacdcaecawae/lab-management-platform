"""Complete processing-run UI scenario; imports the pilot's synthetic browser helpers.

Run only via the same isolated harness as scenarios.py. ORM use below is read-only.
No script is executed and the synthetic git URL is stored as text, never fetched.
"""
from hashlib import sha256

from selenium.webdriver.common.keys import Keys

from scenarios import (
    APP, EVIDENCE, By, WebDriverWait, ec, browser, login, visit, button,
    option, field_control, label_input, visible, body_has, record_path, screenshot, evidence,
)
from datasets.models import Dataset
from datasets.versions import current_version
from research.models import ProcessingRun


TITLE = "合成验证-完整处理记录"
REASON = "合成验证-请补充处理结论"


def upload(session, dataset, name, data):
    path = EVIDENCE.parent / name
    path.write_bytes(data)
    button(session, "上传文件")
    WebDriverWait(session, 12).until(ec.presence_of_element_located((By.CSS_SELECTOR, "input[type=file]"))).send_keys(str(path))
    body_has(session, "已上传 1 个文件")
    WebDriverWait(session, 12).until(lambda _: dataset.files.filter(name=name).exists())
    row = dataset.files.get(name=name)
    assert row.sha256 == sha256(data).hexdigest() and row.size == len(data)
    with row.file.open("rb") as stored:
        assert stored.read() == data


def create_dataset(session, name, kind, kind_label, filename, data):
    visit(session, "/datasets")
    button(session, "新建数据集").click()
    option(session, "项目", "导波螺栓松动")
    label_input(session, "名称").send_keys(name)
    visible(session, By.XPATH, f"//div[@role='dialog']//label[contains(@class,'el-radio')][normalize-space(.)='{kind_label}']").click()
    button(session, "保存", "//div[@role='dialog']").click()  # FormDialog's main button
    path = record_path(session, "datasets")
    dataset = Dataset.objects.get(pk=int(path.rsplit("/", 1)[1]), owner__username="s_a")
    assert dataset.kind == kind and dataset.name == name
    upload(session, dataset, filename, data)
    screenshot(session, f"processing-{kind}-uploaded")
    return dataset


def processing(stack):
    student = browser(stack)
    login(student, "s_a")
    raw = create_dataset(student, "合成处理-输入", "raw", "原始数据", "processing-input.csv", b"t,amp\n0,1\n")
    script = create_dataset(student, "合成处理-脚本", "script", "脚本", "processing.py", b"# synthetic fixture, never executed\n")
    result = create_dataset(student, "合成处理-结果", "result", "处理结果", "processing-output.csv", b"mean\n1\n")

    visit(student, "/runs")
    button(student, "新建处理记录").click()
    option(student, "项目", "导波螺栓松动")
    label_input(student, "任务名称").send_keys(TITLE)
    # An incomplete draft must remain a draft when submit validation fails.
    button(student, "提交").click()
    body_has(student, "至少需要 1 个输入数据")
    detail = record_path(student, "runs")
    run = ProcessingRun.objects.get(title=TITLE, owner__username="s_a")
    assert run.status == "draft" and not run.data_versions and run.submitted_at is None
    screenshot(student, "processing-incomplete-rejected")

    option(student, "输入数据集（只能选择自己的数据集）", raw.name)
    # Multiple-select stays open after choosing an input and overlaps the script field.
    # Dismiss it with the same keyboard interaction a user can perform, not a JS click.
    inputs_combo = field_control(student, "输入数据集（只能选择自己的数据集）", "input[@role='combobox']")
    inputs_listbox = inputs_combo.get_attribute("aria-controls")
    assert inputs_listbox
    inputs_combo.send_keys(Keys.ESCAPE)
    WebDriverWait(student, 12).until(ec.invisibility_of_element_located((By.ID, inputs_listbox)))
    # The script group has multiple controls, so Element Plus renders its label as a div.
    visible(student, By.CSS_SELECTOR, ".script .el-select__wrapper").click()
    combo = visible(student, By.CSS_SELECTOR, ".script input[role=combobox]")
    listbox = combo.get_attribute("aria-controls")
    assert listbox
    visible(student, By.XPATH, f"//*[@id='{listbox}']//*[@role='option'][contains(normalize-space(.),'{script.name}')]").click()
    label_input(student, "方法版本").send_keys("synthetic-v1")
    label_input(student, "运行环境").send_keys("Python 3.12 synthetic-only")
    button(student, "添加参数").click()
    visible(student, By.CSS_SELECTOR, 'input[aria-label="参数名"]').send_keys("window")
    visible(student, By.CSS_SELECTOR, 'input[aria-label="值"]').send_keys("16")
    option(student, "结果数据集", result.name)
    label_input(student, "结论", "textarea").send_keys("合成数据处理完成，仅验证记录流程")
    button(student, "保存草稿").click()
    body_has(student, "草稿已保存")
    run.refresh_from_db()
    assert run.status == "draft" and run.inputs.get().pk == raw.pk
    assert run.script_dataset_id == script.pk and run.output_dataset_id == result.pk
    assert run.params == {"window": "16"} and run.environment == "Python 3.12 synthetic-only"
    assert run.method_version == "synthetic-v1" and not run.script_repo
    screenshot(student, "processing-complete-draft")

    button(student, "提交").click()
    body_has(student, "记录已锁定；如需修改，请联系导师退回。")
    run.refresh_from_db()
    pinned = {str(d.pk): current_version(d) for d in (raw, script, result)}
    assert run.status == "submitted" and run.submitted_at and run.data_versions == pinned
    assert not label_input(student, "任务名称").is_enabled()
    assert not student.find_elements(By.XPATH, "//button[normalize-space(.)='保存草稿' or normalize-space(.)='提交']")
    screenshot(student, "processing-submitted")

    visit(student, f"/datasets/{raw.pk}")
    upload(student, raw, "processing-input-2.csv", b"t,amp\n1,2\n")
    visit(student, detail)
    body_has(student, "提交后有新增")
    run.refresh_from_db()
    assert run.data_versions == pinned and current_version(raw) != pinned[str(raw.pk)]
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

    # Switch to git metadata for the second valid submission; no remote URL is visited.
    visit(student, detail)
    visible(student, By.XPATH, "//label[contains(@class,'el-radio')][normalize-space(.)='git 仓库']").click()
    visible(student, By.CSS_SELECTOR, 'input[placeholder="仓库地址"]').send_keys("https://example.invalid/synthetic-processing.git")
    visible(student, By.CSS_SELECTOR, 'input[placeholder="commit"]').send_keys("a" * 40)
    visible(student, By.CSS_SELECTOR, 'input[placeholder="入口脚本，如 src/run.py"]').send_keys("src/process.py")
    label_input(student, "结论", "textarea").send_keys("；已补充处理结论")
    button(student, "提交").click()
    body_has(student, "记录已锁定；如需修改，请联系导师退回。")
    run.refresh_from_db()
    final_versions = {str(d.pk): current_version(d) for d in (raw, result)}
    assert run.status == "submitted" and run.data_versions == final_versions
    assert run.script_dataset_id is None and run.script_commit == "a" * 40
    assert run.script_path == "src/process.py" and "已补充处理结论" in run.conclusion
    assert ProcessingRun.objects.filter(title=TITLE, owner__username="s_a").count() == 1
    screenshot(student, "processing-git-resubmitted")

    for who in ("s_b", "x_mgr"):
        outsider = browser(stack)
        login(outsider, who)
        visit(outsider, detail)
        body_has(outsider, "记录不存在或无权查看")
        screenshot(outsider, f"processing-isolation-{who}")
    evidence("processing-db", {"id": run.pk, "status": run.status, "first_pinned": pinned,
                              "final_pinned": final_versions, "script_commit": run.script_commit,
                              "params": run.params, "history_count": run.history.count()})

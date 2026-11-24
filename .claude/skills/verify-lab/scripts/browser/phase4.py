"""Phase-four UI flows against the pilot's isolated synthetic fixtures."""

from datetime import timedelta
from hashlib import sha256

from django.utils import timezone
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as ec

from achievements.models import Achievement
from knowledge.models import Doc
from meetings.models import ActionItem, Meeting


def select_aria(ui, session, label, text):
    combo_selector = f"input[role=combobox][aria-label='{label}']"
    wrapper = ui.visible(session, By.CSS_SELECTOR, f".el-select__wrapper:has({combo_selector})")
    wrapper.click()
    combo = wrapper.find_element(By.CSS_SELECTOR, combo_selector)
    listbox = combo.get_attribute("aria-controls")
    assert listbox
    ui.visible(session, By.XPATH, f"//*[@id='{listbox}']//*[@role='option'][normalize-space(.)='{text}']").click()


def replace_text(control, text):
    control.send_keys(Keys.CONTROL, "a")
    control.send_keys(text)


def meetings(ui, stack):
    manager = ui.browser(stack)
    student = ui.browser(stack)
    ui.login(manager, "mgr")
    ui.login(student, "s_a")
    ui.visit(manager, "/meetings")
    ui.button(manager, "新建组会").click()
    title, topic, content = "合成组会验收", "合成报告主题", "合成迟到行动项"
    replace_text(ui.label_input(manager, "标题"), title)
    select_aria(ui, manager, "汇报人", "学生甲")
    ui.visible(manager, By.CSS_SELECTOR, "input[aria-label='汇报内容']").send_keys(topic)
    ui.button(manager, "添加行动项").click()
    select_aria(ui, manager, "负责人", "学生甲")
    ui.visible(manager, By.CSS_SELECTOR, "input[aria-label='事项']").send_keys(content)
    due = timezone.localdate() - timedelta(days=1)
    date_field = ui.visible(manager, By.CSS_SELECTOR, "input[placeholder='截止日期']")
    date_field.send_keys(due.isoformat(), Keys.TAB)
    assert date_field.get_attribute("value") == due.isoformat()
    ui.button(manager, "保存").click()
    detail = ui.record_path(manager, "meetings")
    meeting = Meeting.objects.get(title=title)
    action = meeting.actions.get(content=content)
    assert action.due_date == due and action.owner.username == "s_a"
    assert meeting.agenda.get().topic == topic

    ui.visit(student, "/")
    # workbench row: kind tag, then the title, then the due date (red when late)
    row = ui.visible(student, By.XPATH, f"//li[a[.//span[contains(@class,'title')][normalize-space(.)='{content}']]]")
    due_badge = row.find_element(By.CSS_SELECTOR, "span.late")
    assert due.isoformat() in due_badge.text
    ui.screenshot(student, "meetings-overdue-workbench")
    row.find_element(By.TAG_NAME, "a").click()
    WebDriverWait(student, 12).until(lambda b: b.current_url == ui.APP + detail)
    ui.body_has(student, "（已过期）")
    ui.screenshot(student, "meetings-overdue-detail")

    action_row = f"//tr[td[normalize-space(.)='{content}']]"
    ui.visible(student, By.XPATH, action_row + "//span[contains(@class,'el-checkbox__inner')]").click()

    def done(_):
        action.refresh_from_db()
        return action.done_at

    done_at = WebDriverWait(student, 12).until(done)
    ui.visible(student, By.XPATH, action_row + "//span[contains(@class,'el-checkbox__input') and contains(@class,'is-checked')]")
    ui.screenshot(student, "meetings-action-done")

    # Refresh manager to model a normal edit of the now-completed action, not a stale UI.
    ui.visit(manager, detail)
    ui.button(manager, "编辑").click()
    edited = "合成事项编辑后仍完成"
    replace_text(ui.visible(manager, By.CSS_SELECTOR, "input[aria-label='事项']"), edited)
    ui.button(manager, "保存").click()
    new_row = f"//tr[td[normalize-space(.)='{edited}']]"
    ui.visible(manager, By.XPATH, new_row + "//span[contains(@class,'el-checkbox__input') and contains(@class,'is-checked')]")
    action.refresh_from_db()
    assert action.content == edited and action.done_at == done_at
    assert action.owner.username == "s_a" and action.due_date == due
    assert meeting.actions.count() == 1
    ui.screenshot(manager, "meetings-edit-retained-completion")

    ui.button(manager, "编辑").click()
    ui.button(manager, "删除组会").click()
    ui.visible(manager, By.CSS_SELECTOR, ".el-message-box__btns .el-button--primary").click()
    ui.wait_path(manager, "/meetings")
    assert not Meeting.objects.filter(pk=meeting.pk).exists()
    assert not ActionItem.objects.filter(pk=action.pk).exists()
    assert not meeting.agenda.exists()
    ui.visit(manager, detail)
    ui.body_has(manager, "记录不存在或无权查看")
    ui.screenshot(manager, "meetings-deleted")
    ui.evidence("meetings-db", {"completion_preserved": True, "meeting_removed": True, "action_removed": True, "agenda_removed": True})


def pdf_bytes(x):
    """A minimal valid one-page PDF whose rectangle offset distinguishes its bytes."""
    stream = f"q\n{x} 10 20 20 re S\nQ\n".encode("ascii")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 72 72] /Contents 4 0 R >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"endstream",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for index, obj in enumerate(objects, 1):
        offsets.append(len(out))
        out.extend(f"{index} 0 obj\n".encode() + obj + b"\nendobj\n")
    xref = len(out)
    out.extend(b"xref\n0 5\n0000000000 65535 f \n")
    for offset in offsets:
        out.extend(f"{offset:010d} 00000 n \n".encode())
    out.extend(f"trailer\n<< /Size 5 /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode())
    return bytes(out)


def achievements(ui, stack):
    author = ui.browser(stack)
    ui.login(author, "s_a")
    ui.visit(author, "/achievements")
    first, other = "合成论文甲的全文替换", "合成论文乙的筛选对照"

    def create(title, member, status):
        ui.button(author, "登记成果").click()
        ui.label_input(author, "标题").send_keys(title)
        ui.label_input(author, "作者（按署名顺序，含外单位）").send_keys(member)
        ui.option(author, "状态", status)
        ui.option(author, "本组成员", member)
        ui.button(author, "保存").click()
        ui.button(author, "上传全文")

    create(first, "学生甲", "已录用")
    record = Achievement.objects.get(title=first)
    assert record.members.get().username == "s_a" and record.status == Achievement.Status.ACCEPTED

    def upload(name, x):
        payload = pdf_bytes(x)
        path = ui.EVIDENCE.parent / name
        path.write_bytes(payload)
        selector = ".el-dialog input[type=file][accept='.pdf']"
        WebDriverWait(author, 12).until(ec.presence_of_element_located((By.CSS_SELECTOR, selector))).send_keys(str(path))
        ui.button(author, name)  # the file name opens the preview (a link-styled button since PR #51)
        record.refresh_from_db()
        assert record.fulltext_name == name
        with record.fulltext.open("rb") as stored:
            assert stored.read() == payload
        return record.fulltext.name, sha256(payload).hexdigest()

    old_name, old_digest = upload("phase4-initial.pdf", 10)
    ui.button(author, "替换全文")
    new_name, new_digest = upload("phase4-replacement.pdf", 15)
    assert old_name != new_name and old_digest != new_digest
    WebDriverWait(author, 12).until(lambda _: not record.fulltext.storage.exists(old_name))
    assert not author.find_elements(By.XPATH, "//button[normalize-space(.)='phase4-initial.pdf']")
    ui.screenshot(author, "achievements-fulltext-replaced")
    ui.button(author, "取消").click()

    create(other, "学生乙", "投稿中")
    ui.button(author, "取消").click()
    ui.button(author, other)
    select_aria(ui, author, "成员", "学生甲")
    ui.button(author, first)
    WebDriverWait(author, 12).until_not(ec.presence_of_element_located((By.XPATH, f"//button[normalize-space(.)='{other}']")))
    assert Achievement.objects.get(title=other).members.get().username == "s_b"
    ui.screenshot(author, "achievements-member-filter")
    ui.evidence("achievements-db", {"old_sha256": old_digest, "new_sha256": new_digest,
                                   "old_file_removed": True, "member_filter": True})


def knowledge(ui, stack):
    student = ui.browser(stack)
    ui.login(student, "s_a")
    ui.visit(student, "/knowledge")
    tag = "synthetic-phase4-only"
    target, control = "合成标签目标", "合成标签对照"

    def create(title, item):
        ui.button(student, "新建文档").click()
        ui.label_input(student, "标题").send_keys(title)
        ui.field_control(student, "标签", "div[contains(@class,'el-select__wrapper')]").click()
        combo = ui.field_control(student, "标签", "input[@role='combobox']")
        combo.send_keys(item)
        listbox = combo.get_attribute("aria-controls")
        ui.visible(student, By.XPATH, f"//*[@id='{listbox}']//*[@role='option'][normalize-space(.)='{item}']").click()
        ui.button(student, "保存").click()
        ui.body_has(student, "已新建，可以上传文件")
        ui.button(student, "取消").click()

    create(target, tag)
    create(control, "synthetic-phase4-control")
    assert Doc.objects.get(title=target).tags == [tag]
    assert Doc.objects.get(title=control).tags != [tag]
    search = ui.visible(student, By.CSS_SELECTOR, "input[placeholder='搜索标题、标签、说明、设备']")
    search.send_keys(tag, Keys.TAB)
    wanted = f"//tr[td[normalize-space(.)='{target}']]"
    unwanted = f"//tr[td[normalize-space(.)='{control}']]"
    ui.visible(student, By.XPATH, wanted)
    WebDriverWait(student, 12).until_not(ec.presence_of_element_located((By.XPATH, unwanted)))
    ui.screenshot(student, "knowledge-tag-filter")
    ui.evidence("knowledge-db", {"target_tag": tag, "tag_in_search_results": True, "control_excluded": True})

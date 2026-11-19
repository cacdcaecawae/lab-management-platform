"""Synthetic specimen filters using ordinary browser interactions and read-only DB evidence."""
from contextlib import ExitStack

from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as ec
from selenium.webdriver.support.ui import WebDriverWait

from specimens.models import Specimen, SpecimenLoan

MINE = "VERIFY-MINE"
PEER = "VERIFY-PEER"
RETIRED = "VERIFY-RETIRED"
RETURNED = "VERIFY-RETURNED"
FOREIGN = "VERIFY-OTHER-GROUP"


def check_specimen_filters(stack, *, browser, login, visit, visible, button, label_input, body_has,
                           record_path, screenshot, evidence):
    rows = {}

    def pick(session, where, label, value):
        box = f"{where}//div[contains(@class,'el-select')][.//input[@aria-label='{label}']]"
        visible(session, By.XPATH, f"{box}//div[contains(@class,'el-select__wrapper')]").click()
        # Non-filterable selects may keep their readonly input at zero width after
        # opening. It still identifies the linked listbox; only the option must be visible.
        combo = WebDriverWait(session, 12).until(ec.presence_of_element_located(
            (By.XPATH, f"{box}//input[@role='combobox'][@aria-label='{label}']")
        ))
        listbox = combo.get_attribute("aria-controls")
        assert listbox
        visible(session, By.XPATH, f"//*[@id='{listbox}']//*[@role='option'][normalize-space(.)='{value}']").click()

    def create(session, code, kind=None, status=None):
        visit(session, "/specimens")
        button(session, "新增试件").click()
        label_input(session, "编号").send_keys(code)
        label_input(session, "名称").send_keys(f"合成试件 {code}")
        dialog = "//div[@role='dialog']"
        if kind:
            pick(session, dialog, "类别", kind)
        if status:
            visible(session, By.XPATH, f"{dialog}//label[contains(@class,'el-radio')][normalize-space(.)='{status}']").click()
        button(session, "保存", dialog).click()
        path = record_path(session, "specimens")
        body_has(session, "借用记录")
        row = Specimen.objects.get(pk=int(path.rsplit("/", 1)[-1]), code=code)
        rows[code] = row
        return path

    def borrow(session, path, person):
        visit(session, path)
        button(session, "借用").click()
        button(session, "借用", "//div[@role='dialog']").click()
        body_has(session, f"{person} 借用中")

    def exact_codes(session, name, expected):
        expected = set(expected)

        def current(s):
            table = s.find_element(By.CSS_SELECTOR, "main .el-table")
            if table.find_elements(By.CSS_SELECTOR, ".el-loading-mask"):
                return False
            present = {a.text for a in table.find_elements(By.CSS_SELECTOR, 'a[href^="/specimens/"]')
                       if a.is_displayed()}
            return present == expected

        WebDriverWait(session, 12).until(ec.visibility_of_element_located((By.CSS_SELECTOR, "main .el-table")))
        WebDriverWait(session, 12).until(current, f"{name}: expected exact visible specimen codes {sorted(expected)}")
        screenshot(session, f"specimen-filters-{name}")

    with ExitStack() as fixture_browsers:
        mgr = browser(fixture_browsers)
        login(mgr, "mgr")
        mine_path = create(mgr, MINE)
        peer_path = create(mgr, PEER, "试样")
        create(mgr, RETIRED, "对比试块", "停用")
        returned_path = create(mgr, RETURNED, "试样")
        outsider = browser(fixture_browsers)
        login(outsider, "x_mgr")
        create(outsider, FOREIGN)
        visit(outsider, "/specimens")
        exact_codes(outsider, "other-group", [FOREIGN])
        assert rows[FOREIGN].group_id != rows[MINE].group_id

    student = browser(stack)
    login(student, "s_a")
    borrow(student, mine_path, "学生甲")
    borrow(student, returned_path, "学生甲")
    button(student, "登记归还").click()
    visible(student, By.CSS_SELECTOR, '.el-message-box input[placeholder="归还说明"]').send_keys("合成验证：完好")
    visible(student, By.CSS_SELECTOR, ".el-message-box__btns .el-button--primary").click()
    body_has(student, "已登记归还")
    peer = browser(stack)
    login(peer, "s_b")
    borrow(peer, peer_path, "学生乙")

    visit(student, "/specimens")
    exact_codes(student, "unfiltered", [MINE, PEER, RETIRED, RETURNED])
    toolbar = "//main//div[contains(@class,'page-toolbar')]"
    pick(student, toolbar, "类别", "试样")
    exact_codes(student, "category", [PEER, RETURNED])
    visit(student, "/specimens")
    exact_codes(student, "reset-category", [MINE, PEER, RETIRED, RETURNED])
    pick(student, toolbar, "状态", "停用")
    exact_codes(student, "status", [RETIRED])
    visit(student, "/specimens")
    exact_codes(student, "reset-status", [MINE, PEER, RETIRED, RETURNED])
    visible(student, By.XPATH, f"{toolbar}//label[normalize-space(.)='只看借出的']").click()
    exact_codes(student, "borrowed", [MINE, PEER])
    visible(student, By.XPATH, f"{toolbar}//label[normalize-space(.)='只看借出的']").click()
    exact_codes(student, "reset-borrowed", [MINE, PEER, RETIRED, RETURNED])
    visible(student, By.XPATH, f"{toolbar}//label[normalize-space(.)='我借的']").click()
    exact_codes(student, "mine", [MINE])

    expected = {MINE: ("s_a", False), PEER: ("s_b", False), RETURNED: ("s_a", True)}
    loans = {
        loan.specimen.code: (loan.borrower.username, loan.returned_at is not None)
        for loan in SpecimenLoan.objects.select_related("specimen", "borrower").filter(
            specimen_id__in=[row.pk for row in rows.values()]
        )
    }
    assert loans == expected
    assert rows[PEER].kind == "sample" and rows[RETIRED].status == "retired"
    evidence("specimen-filters-db", {"loans": loans, "groups": {code: row.group_id for code, row in rows.items()}})

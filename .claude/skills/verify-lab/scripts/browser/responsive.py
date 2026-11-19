"""390x844 synthetic menu survey. DOM reads are diagnostics, never application writes."""
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as ec

# Only root/document overflow is a failure. Scrollable tables are separately reported:
# their wide contents can be legitimate, provided their viewport fits the page.
METRICS = r"""
const root = document.documentElement, body = document.body;
const width = root.clientWidth;
const visible = e => e.getClientRects().length && getComputedStyle(e).visibility !== 'hidden';
const box = e => { const r=e.getBoundingClientRect(); return {
  tag:e.tagName, classes:String(e.className).slice(0,120),
  left:r.left, right:r.right, width:r.width,
  clientWidth:e.clientWidth, scrollWidth:e.scrollWidth,
  overflowX:getComputedStyle(e).overflowX
}; };
const tables = [...document.querySelectorAll('.el-table,.el-table__body-wrapper,.el-scrollbar__wrap')]
  .filter(visible).map(box);
const outside = [...document.querySelectorAll('main *, header *')].filter(visible)
  .filter(e => {
    const r=e.getBoundingClientRect();
    if (r.left>=-1 && r.right<=width+1) return false;
    // Content of a bounded horizontal scroller is not page-level overflow.
    for(let p=e.parentElement;p && p!==body;p=p.parentElement){
      const s=getComputedStyle(p), b=p.getBoundingClientRect();
      if(['auto','scroll','hidden','clip'].includes(s.overflowX) && b.left>=-1 && b.right<=width+1)
        return false;
    }
    return true;
  }).slice(0,30).map(box);
return {innerWidth,innerHeight,devicePixelRatio,clientWidth:width,
  rootScrollWidth:root.scrollWidth,bodyScrollWidth:body.scrollWidth,
  visualViewport:visualViewport ? {width:visualViewport.width,height:visualViewport.height,scale:visualViewport.scale}:null,
  horizontalOverflow:Math.max(root.scrollWidth,body.scrollWidth)-width,
  outside,tableScrollers:tables};
"""


def responsive(stack, helpers):
    browser, login = helpers.browser, helpers.login
    visible, screenshot, evidence = helpers.visible, helpers.screenshot, helpers.evidence
    results, failures = [], []
    # A manager sees all business entries; ops sees the separate system page.
    for role in ('mgr', 'ops'):
        session = browser(stack)
        session.execute_cdp_cmd('Emulation.setDeviceMetricsOverride', {
            'width': 390, 'height': 844, 'deviceScaleFactor': 3, 'mobile': True,
        })
        session.execute_cdp_cmd('Emulation.setTouchEmulationEnabled', {'enabled': True, 'maxTouchPoints': 1})
        login(session, role)
        menu_button = 'button[aria-label="打开菜单"]'
        visible(session, By.CSS_SELECTOR, menu_button).click()
        visible(session, By.CSS_SELECTOR, '.nav-drawer')
        names = [e.text.strip() for e in session.find_elements(By.CSS_SELECTOR, '.nav-drawer [role=menuitem]') if e.is_displayed()]
        assert names and len(names) == len(set(names)), names
        evidence(f'responsive-{role}-menu', names)
        screenshot(session, f'responsive-{role}-menu')
        # Close without selecting the already-active route (its watcher would not fire).
        session.find_element(By.TAG_NAME, 'body').send_keys('\ue00c')
        WebDriverWait(session, 12).until(ec.invisibility_of_element_located((By.CSS_SELECTOR, '.nav-drawer')))
        for i, name in enumerate(names):
            visible(session, By.CSS_SELECTOR, menu_button).click()
            item = visible(session, By.XPATH, f"//div[contains(@class,'nav-drawer')]//*[@role='menuitem'][normalize-space(.)='{name}']")
            item.click()
            WebDriverWait(session, 12).until(lambda s: any(
                e.text.strip() == name or e.get_attribute('textContent').strip() == name
                for e in s.find_elements(By.CSS_SELECTOR, '.app-menu .el-menu-item.is-active')
            ))
            # The selected active route can leave the drawer open; dismiss via Escape.
            session.find_element(By.TAG_NAME, 'body').send_keys('\ue00c')
            WebDriverWait(session, 12).until(ec.invisibility_of_element_located((By.CSS_SELECTOR, '.nav-drawer')))
            visible(session, By.CSS_SELECTOR, 'main')
            WebDriverWait(session, 12).until(lambda s: not any(e.is_displayed() for e in s.find_elements(By.CSS_SELECTOR, '.el-loading-mask')))
            # Wait for two animation frames after fonts/layout; do not mutate app state.
            session.execute_async_script('const done=arguments[0]; document.fonts.ready.then(()=>requestAnimationFrame(()=>requestAnimationFrame(done)));')
            metrics = session.execute_script(METRICS)
            metrics.update(role=role, menu=name, url=session.current_url)
            results.append(metrics)
            screenshot(session, f'responsive-{role}-{i:02d}')
            evidence('responsive-metrics', results)  # retain partial evidence on later failure
            if metrics['clientWidth'] != 390 or metrics['innerHeight'] != 844 or metrics['horizontalOverflow'] > 1:
                failures.append({'menu': name, 'role': role, 'metrics': metrics})
    evidence('responsive-summary', {'viewport': '390x844x3 mobile/touch', 'pages': len(results), 'failures': failures,
        'limitations': ['Synthetic seed only; no populated long tables/detail forms.', 'Chromium emulation is not physical mobile Safari/Chrome.', 'Screenshots require visual inspection for clipped controls even without root overflow.']})
    assert not failures, f'Responsive viewport/overflow failures: {[f["menu"] for f in failures]}'

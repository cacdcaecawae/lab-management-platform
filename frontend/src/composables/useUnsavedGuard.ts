import { nextTick, onBeforeUnmount, onMounted } from 'vue'
import { onBeforeRouteLeave, onBeforeRouteUpdate } from 'vue-router'
import { ElMessageBox } from 'element-plus'

type Page = { ask: () => true | Promise<boolean>; leave: () => void }
const onScreen = new Set<Page>()

// Logging out (SideNav): ask while the session can still save, because a logged-out page counts as read-only and
// would no longer ask. After 离开 the page stops asking, so the way to the login page does not ask again.
export async function leavePage() {
  for (const page of onScreen) if (!(await page.ask())) return false
  for (const page of onScreen) page.leave()
  return true
}

// Edit pages: ask before leaving with unsaved changes, whether by a tab, the menu, back, or closing the browser tab.
// The form counts as changed when it no longer matches the snapshot taken by markSaved() (call it after filling the
// form from a load or a save), or when unsaved() says something on screen is not in the form yet (a parameter value
// without a name). Only while editable() is true: a read-only record has nothing to lose.
export function useUnsavedGuard(form: object, editable: () => boolean, unsaved?: () => boolean) {
  let saved = JSON.stringify(form)
  let left = false
  const dirty = () => !left && editable() && (JSON.stringify(form) !== saved || !!unsaved?.())
  function markSaved() {
    saved = JSON.stringify(form) // now: a save that moves to the new record's address must not ask
    void nextTick(() => (saved = JSON.stringify(form))) // and again once child editors have settled the form
  }
  const ask = () =>
    !dirty() ||
    ElMessageBox.confirm('有未保存的修改，离开后会丢失。确定离开？', '离开这一页', {
      confirmButtonText: '离开',
      cancelButtonText: '留下',
      type: 'warning',
    }).then(
      () => true,
      () => false,
    )
  onBeforeRouteLeave(ask)
  onBeforeRouteUpdate((to, from) => to.params.id === from.params.id || ask())
  const onUnload = (e: BeforeUnloadEvent) => dirty() && e.preventDefault()
  const page: Page = { ask, leave: () => (left = true) }
  onMounted(() => {
    window.addEventListener('beforeunload', onUnload)
    onScreen.add(page)
  })
  onBeforeUnmount(() => {
    window.removeEventListener('beforeunload', onUnload)
    onScreen.delete(page)
  })
  return { markSaved }
}

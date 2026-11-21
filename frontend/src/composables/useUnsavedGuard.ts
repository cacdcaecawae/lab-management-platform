import { nextTick, onBeforeUnmount, onMounted } from 'vue'
import { onBeforeRouteLeave, onBeforeRouteUpdate } from 'vue-router'
import { ElMessageBox } from 'element-plus'

// Edit pages: ask before leaving with unsaved changes, whether by a tab, the menu, back, or closing the browser tab.
// The form counts as changed when it no longer matches the snapshot taken by markSaved() (call it after filling the
// form from a load or a save). Only while editable() is true: a read-only record has nothing to lose.
export function useUnsavedGuard(form: object, editable: () => boolean) {
  let saved = JSON.stringify(form)
  const dirty = () => editable() && JSON.stringify(form) !== saved
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
  onMounted(() => window.addEventListener('beforeunload', onUnload))
  onBeforeUnmount(() => window.removeEventListener('beforeunload', onUnload))
  return { markSaved }
}

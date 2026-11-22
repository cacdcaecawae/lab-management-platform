import { afterEach, expect, it, vi } from 'vitest'
import { defineComponent, reactive } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { ElMessageBox } from 'element-plus'
import { leavePage, useUnsavedGuard } from './useUnsavedGuard'

const mounted: { unmount: () => void }[] = []
afterEach(() => {
  mounted.splice(0).forEach((w) => w.unmount()) // a page left on screen would still be asked by leavePage()
  vi.restoreAllMocks()
})

async function setup(editable: boolean | (() => boolean) = true, unsaved?: () => boolean) {
  const form = reactive({ title: '' })
  const canEdit = typeof editable === 'function' ? editable : () => editable
  let markSaved!: () => void
  const Edit = defineComponent({ setup: () => void ({ markSaved } = useUnsavedGuard(form, canEdit, unsaved)), template: '<div />' })
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/edit', component: Edit },
      { path: '/list', component: { template: '<div />' } },
    ],
  })
  await router.push('/edit')
  mounted.push(mount({ template: '<RouterView />' }, { global: { plugins: [router] } }))
  await flushPromises()
  return { form, router, markSaved: () => markSaved() }
}

it('asks before leaving with unsaved changes and stays when told to', async () => {
  const confirm = vi.spyOn(ElMessageBox, 'confirm').mockRejectedValue('cancel')
  const { form, router } = await setup()
  await router.push('/list') // nothing changed: no question
  expect(confirm).not.toHaveBeenCalled()
  await router.push('/edit')
  await flushPromises()
  form.title = '改了'
  await router.push('/list')
  expect(confirm).toHaveBeenCalledOnce()
  expect(router.currentRoute.value.path).toBe('/edit')
  confirm.mockResolvedValue('confirm' as never)
  await router.push('/list')
  expect(router.currentRoute.value.path).toBe('/list')
})

it('asks about something on screen that is not in the form yet', async () => {
  // a parameter value typed without its name: the form object has not changed
  const confirm = vi.spyOn(ElMessageBox, 'confirm').mockRejectedValue('cancel')
  let unnamedValue = false
  const { router } = await setup(true, () => unnamedValue)
  unnamedValue = true
  await router.push('/list')
  expect(confirm).toHaveBeenCalledOnce()
  expect(router.currentRoute.value.path).toBe('/edit')
})

it('logging out asks while the page can still save, then does not ask again on the way out', async () => {
  // logged out, the record counts as read-only and the page would no longer ask
  const confirm = vi.spyOn(ElMessageBox, 'confirm').mockRejectedValue('cancel')
  let loggedIn = true
  const { form, router } = await setup(() => loggedIn)
  form.title = '改了'
  expect(await leavePage()).toBe(false) // 留下
  confirm.mockResolvedValue('confirm' as never)
  expect(await leavePage()).toBe(true) // 离开
  expect(confirm).toHaveBeenCalledTimes(2)
  loggedIn = false
  await router.push('/list')
  expect(router.currentRoute.value.path).toBe('/list')
  expect(confirm).toHaveBeenCalledTimes(2)
  expect(await leavePage()).toBe(true) // no edit page on screen: nothing to ask
})

it('does not ask after saving, or on a read-only record', async () => {
  const confirm = vi.spyOn(ElMessageBox, 'confirm').mockRejectedValue('cancel')
  const saved = await setup()
  saved.form.title = '保存了'
  saved.markSaved()
  await saved.router.push('/list')
  expect(saved.router.currentRoute.value.path).toBe('/list')
  const readonly = await setup(false)
  readonly.form.title = '只读'
  await readonly.router.push('/list')
  expect(readonly.router.currentRoute.value.path).toBe('/list')
  expect(confirm).not.toHaveBeenCalled()
})

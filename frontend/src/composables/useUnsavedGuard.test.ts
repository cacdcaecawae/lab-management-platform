import { afterEach, expect, it, vi } from 'vitest'
import { defineComponent, reactive } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { ElMessageBox } from 'element-plus'
import { useUnsavedGuard } from './useUnsavedGuard'

afterEach(() => vi.restoreAllMocks())

async function setup(editable = true) {
  const form = reactive({ title: '' })
  let markSaved!: () => void
  const Edit = defineComponent({ setup: () => void ({ markSaved } = useUnsavedGuard(form, () => editable)), template: '<div />' })
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/edit', component: Edit },
      { path: '/list', component: { template: '<div />' } },
    ],
  })
  await router.push('/edit')
  mount({ template: '<RouterView />' }, { global: { plugins: [router] } })
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

import { flushPromises, mount } from '@vue/test-utils'
import { defineComponent, h } from 'vue'
import { createMemoryHistory, createRouter, useRoute } from 'vue-router'
import { ElMessageBox } from 'element-plus'
import { expect, it, vi } from 'vitest'
import RoutePage from './RoutePage.vue'
import { replaceSavedEditor } from '@/router/saved-editor'
import { useUnsavedGuard } from '@/composables/useUnsavedGuard'

it('lets a page that is still uploading keep going when its first save rewrites the address', async () => {
  const confirm = vi.spyOn(ElMessageBox, 'confirm')
  // e.g. a new experiment saved by its first file upload: the upload is running while /new becomes /<id>
  const uploading = defineComponent({
    setup() {
      useUnsavedGuard({}, () => true, () => true)
      return () => h('p', 'editor')
    },
  })
  const router = createRouter({ history: createMemoryHistory(), routes: [
    { name: 'experiment-new', path: '/experiments/new', component: uploading },
    { name: 'experiment-edit', path: '/experiments/:id', component: uploading },
    { name: 'elsewhere', path: '/elsewhere', component: { render: () => null } },
  ] })
  await router.push('/experiments/new')
  const wrapper = mount(RoutePage, { global: { plugins: [router] } })
  await replaceSavedEditor(router, router.currentRoute.value, '/experiments/1')
  expect(router.currentRoute.value.fullPath).toBe('/experiments/1')
  expect(confirm).not.toHaveBeenCalled()
  confirm.mockRejectedValueOnce('cancel') // leaving for real still asks, and 留下 keeps the page
  await router.push('/elsewhere')
  expect(confirm).toHaveBeenCalledOnce()
  expect(router.currentRoute.value.fullPath).toBe('/experiments/1')
  wrapper.unmount()
  confirm.mockRestore()
})

it('reloads a second saved editor without resetting the editor on create-to-saved navigation', async () => {
  const seen: string[] = []
  const editor = defineComponent({
    setup() {
      const loaded = String(useRoute().params.id ?? 'new')
      seen.push(loaded)
      return () => h('p', loaded)
    },
  })
  const router = createRouter({ history: createMemoryHistory(), routes: [
    { name: 'experiment-new', path: '/experiments/new', component: editor },
    { name: 'experiment-edit', path: '/experiments/:id', component: editor },
  ] })
  await router.push('/experiments/new')
  const wrapper = mount(RoutePage, { global: { plugins: [router] } })
  await replaceSavedEditor(router, router.currentRoute.value, '/experiments/1')
  await flushPromises()
  expect(seen).toEqual(['new'])
  await router.push('/experiments/2')
  await flushPromises()
  expect(seen).toEqual(['new', '2'])
  expect(wrapper.text()).toBe('2')
  await router.push('/experiments/new')
  await flushPromises()
  expect(wrapper.text()).toBe('new')
  const preSave = router.currentRoute.value
  await router.push('/experiments/1') // same URL as earlier save, ordinary navigation must remount
  await flushPromises()
  expect(seen).toEqual(['new', '2', 'new', '1'])
  expect(wrapper.text()).toBe('1')
  await replaceSavedEditor(router, preSave, '/experiments/99')
  expect(router.currentRoute.value.fullPath).toBe('/experiments/1')
  await router.push('/experiments/new') // returning to the same path is a new route object
  await replaceSavedEditor(router, preSave, '/experiments/99')
  expect(router.currentRoute.value.fullPath).toBe('/experiments/new')
  wrapper.unmount()
})

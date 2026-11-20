import { flushPromises, mount } from '@vue/test-utils'
import { defineComponent, h } from 'vue'
import { createMemoryHistory, createRouter, useRoute } from 'vue-router'
import { expect, it } from 'vitest'
import RoutePage from './RoutePage.vue'
import { replaceSavedEditor } from '@/router/saved-editor'

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

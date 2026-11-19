import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { createMemoryHistory, createRouter } from 'vue-router'
import { expect, it, vi } from 'vitest'
import AchievementsView from './AchievementsView.vue'
import ConsumablesView from './ConsumablesView.vue'

const api = vi.hoisted(() => ({ achievements: vi.fn(), consumables: vi.fn(), other: vi.fn() }))
vi.mock('@/api/achievements', () => ({ achievementsApi: { list: api.achievements, exportUrl: () => '#' } }))
vi.mock('@/api/inventory', () => ({ consumablesApi: { list: api.consumables } }))
vi.mock('@/api/members', () => ({ membersApi: { list: api.other } }))
vi.mock('@/api/projects', () => ({ projectsApi: { list: api.other } }))
vi.mock('@/api/procurement', () => ({ purchasesApi: { list: api.other } }))
vi.mock('@/stores/auth', () => ({ useAuthStore: () => ({ user: { id: 1 }, isManager: false }) }))

it.each([
  ['/achievements', AchievementsView, api.achievements],
  ['/consumables', ConsumablesView, api.consumables],
] as const)('can target the same search result again after showing all at %s', async (path, component, fetch) => {
  const page = { results: [], count: 0, next: null, previous: null }
  api.other.mockResolvedValue(page)
  fetch.mockClear().mockResolvedValue(page)
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path, component }] })
  const target = `${path}?item=17&other=keep#position`
  await router.push(target)
  const view = mount(component, { global: { plugins: [router, ElementPlus], stubs: { HistoryDrawer: true } } })
  try {
    await flushPromises()
    expect(fetch.mock.lastCall?.[0].item).toBe('17')
    const button = view.findAll('button').find(b => b.text() === '显示全部')!
    await button.trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.fullPath).toBe(`${path}?other=keep#position`)
    expect(fetch.mock.lastCall?.[0].item).toBe('')
    await router.push(target)
    await flushPromises()
    expect(fetch.mock.lastCall?.[0].item).toBe('17')
  } finally {
    view.unmount()
  }
})

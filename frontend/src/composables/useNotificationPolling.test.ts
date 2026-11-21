import { afterEach, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { createPinia } from 'pinia'
import { defineComponent } from 'vue'
import { createMemoryHistory, createRouter } from 'vue-router'
import type { Me } from '@/api/types'
import { useAuthStore } from '@/stores/auth'
import { useNotificationsStore } from '@/stores/notifications'
import NotificationsView from '@/modules/notifications/views/NotificationsView.vue'
import { useNotificationPolling } from './useNotificationPolling'

afterEach(() => {
  vi.unstubAllGlobals()
  vi.useRealTimers()
  vi.restoreAllMocks()
})

const Host = defineComponent({
  setup() {
    useNotificationPolling()
    return () => null
  },
})

async function setup() {
  const item = { id: 8, title: '采购申请退回修改', body: '', link: '/purchases/2', created_at: '2026-11-19T00:00:00Z', read_at: null }
  const routes = [{ name: 'root', path: '/' }, { name: 'notifications', path: '/notifications' }, { name: 'purchase', path: '/purchases/2' }]
  const router = createRouter({ history: createMemoryHistory(), routes: routes.map((r) => ({ ...r, component: { template: '<div />' } })) })
  await router.push('/')
  let unread = 1
  const fetch = vi.fn((url: string) => {
    if (url.endsWith('/8/read/')) unread = 0
    return Promise.resolve(new Response(JSON.stringify(
      url.includes('unread-count') ? { count: unread } : { results: [item], count: 1, next: null, previous: null },
    ), { status: 200 }))
  })
  vi.stubGlobal('fetch', fetch)
  const pinia = createPinia()
  useAuthStore(pinia).user = { id: 1, role: 'student', group: { id: 7, name: 'Fixture' } } as Me
  return { router, fetch, pinia, global: { plugins: [router, pinia, ElementPlus] } }
}

it('the notifications page reads an item before opening it, and the unread count follows', async () => {
  vi.spyOn(document, 'visibilityState', 'get').mockReturnValue('visible')
  const { router, fetch, pinia, global } = await setup()
  const host = mount(Host, { global })
  await flushPromises()
  expect(useNotificationsStore(pinia).unread).toBe(1)
  const page = mount(NotificationsView, { global })
  await flushPromises()
  await page.findAll('button').find((button) => button.text().includes('采购申请退回修改'))!.trigger('click')
  await flushPromises()
  expect(fetch).toHaveBeenCalledWith('/api/notifications/8/read/', expect.objectContaining({ method: 'POST' }))
  expect(router.currentRoute.value.path).toBe('/purchases/2')
  expect(useNotificationsStore(pinia).unread).toBe(0)
  page.unmount()
  host.unmount()
})

it('does not poll while hidden and disposes its interval when unmounted', async () => {
  vi.useFakeTimers()
  const visibility = vi.spyOn(document, 'visibilityState', 'get').mockReturnValue('hidden')
  const { fetch, global } = await setup()
  const host = mount(Host, { global })
  await flushPromises()
  expect(fetch).not.toHaveBeenCalled()
  await vi.advanceTimersByTimeAsync(60_000)
  expect(fetch).not.toHaveBeenCalled()
  visibility.mockReturnValue('visible')
  document.dispatchEvent(new Event('visibilitychange'))
  expect(fetch).toHaveBeenCalledTimes(1)
  await vi.advanceTimersByTimeAsync(60_000)
  expect(fetch).toHaveBeenCalledTimes(2)
  host.unmount()
  await vi.advanceTimersByTimeAsync(60_000)
  expect(fetch).toHaveBeenCalledTimes(2)
})

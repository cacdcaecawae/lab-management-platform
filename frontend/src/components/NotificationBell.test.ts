import { afterEach, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { defineComponent, ref } from 'vue'
import { createMemoryHistory, createRouter } from 'vue-router'
import type { Me } from '@/api/types'
import { useAuthStore } from '@/stores/auth'
import NotificationBell from './NotificationBell.vue'

const Popover = defineComponent({
  emits: ['show'],
  setup: () => ({ open: ref(false) }),
  template: '<div><span @click="open=true; $emit(\'show\')"><slot name="reference"/></span><div v-if="open"><slot/></div></div>',
})

afterEach(() => {
  vi.unstubAllGlobals()
  vi.useRealTimers()
  vi.restoreAllMocks()
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
      url.includes('unread-count') ? { count: unread } : { results: [item] },
    ), { status: 200 }))
  })
  vi.stubGlobal('fetch', fetch)
  const pinia = createPinia()
  useAuthStore(pinia).user = { id: 1, role: 'student', group: { id: 7, name: 'Fixture' } } as Me
  const wrapper = mount(NotificationBell, { global: {
    plugins: [router, pinia],
    stubs: {
      ElPopover: Popover,
      ElBadge: { template: '<span><slot /></span>' },
      ElButton: { template: '<button><slot /></button>' },
    },
    directives: { loading: {} },
  } })
  await flushPromises()
  return { wrapper, router, fetch }
}

it('shows the unread count and reads the item before navigating', async () => {
  vi.spyOn(document, 'visibilityState', 'get').mockReturnValue('visible')
  const { wrapper, router, fetch } = await setup()
  const bell = wrapper.get('button[aria-label="通知，1 条未读"]')
  await bell.trigger('click')
  await flushPromises()
  expect(fetch).toHaveBeenCalledWith('/api/notifications/?page_size=10', expect.anything())
  await wrapper.findAll('button').find((button) => button.text().includes('采购申请退回修改'))!.trigger('click')
  await flushPromises()
  expect(fetch).toHaveBeenCalledWith('/api/notifications/8/read/', expect.objectContaining({ method: 'POST' }))
  expect(router.currentRoute.value.path).toBe('/purchases/2')
  expect(wrapper.find('button[aria-label="通知，0 条未读"]').exists()).toBe(true)
  wrapper.unmount()
})

it('does not poll while hidden and disposes its interval when unmounted', async () => {
  vi.useFakeTimers()
  const visibility = vi.spyOn(document, 'visibilityState', 'get').mockReturnValue('hidden')
  const { wrapper, fetch } = await setup()
  expect(fetch).not.toHaveBeenCalled()
  await vi.advanceTimersByTimeAsync(60_000)
  expect(fetch).not.toHaveBeenCalled()
  visibility.mockReturnValue('visible')
  document.dispatchEvent(new Event('visibilitychange'))
  expect(fetch).toHaveBeenCalledTimes(1)
  await vi.advanceTimersByTimeAsync(60_000)
  expect(fetch).toHaveBeenCalledTimes(2)
  wrapper.unmount()
  await vi.advanceTimersByTimeAsync(60_000)
  expect(fetch).toHaveBeenCalledTimes(2)
})

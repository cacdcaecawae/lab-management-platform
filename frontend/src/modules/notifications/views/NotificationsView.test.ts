import { afterEach, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { createPinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'
import type { Me } from '@/api/types'
import { useAuthStore } from '@/stores/auth'
import NotificationsView from './NotificationsView.vue'

afterEach(() => vi.unstubAllGlobals())

it('marks visible account notifications read and reloads the unread page', async () => {
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/', component: { template: '<div />' } }] })
  await router.push('/')
  const item = { id: 8, title: '设备登记使用异常', body: '', link: '/equipment/2', created_at: '2026-11-19T00:00:00Z', read_at: null }
  let cleared = false
  const fetch = vi.fn((url: string) => {
    if (url.includes('read-all')) cleared = true
    const response = url.includes('unread-count') ? { count: 0 }
      : cleared ? { count: 0, results: [] } : { count: 1, results: [item] }
    return Promise.resolve(new Response(JSON.stringify(response), { status: 200 }))
  })
  vi.stubGlobal('fetch', fetch)
  const pinia = createPinia()
  useAuthStore(pinia).user = { id: 1, role: 'manager', group: { id: 7, name: 'Fixture' } } as Me
  const wrapper = mount(NotificationsView, { global: { plugins: [router, pinia, ElementPlus] } })
  await flushPromises()
  expect(wrapper.text()).toContain(item.title)
  await wrapper.get('input[type="checkbox"]').setValue(true)
  await flushPromises()
  expect(fetch.mock.calls.some(([url]) => url.includes('unread=1'))).toBe(true)
  await wrapper.findAll('button').find((button) => button.text() === '全部标为已读')!.trigger('click')
  await flushPromises()
  expect(fetch).toHaveBeenCalledWith('/api/notifications/read-all/', expect.objectContaining({ method: 'POST' }))
  expect(wrapper.text()).toContain('暂无通知')
  wrapper.unmount()
})

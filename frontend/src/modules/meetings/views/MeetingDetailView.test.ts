// A new meeting starts from the minutes outline and can carry over the open items of the latest meeting.
import { afterEach, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { createPinia } from 'pinia'
import { createMemoryHistory, createRouter, RouterView } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import type { Me, Meeting } from '@/api/types'
import MeetingDetailView from './MeetingDetailView.vue'

afterEach(() => vi.unstubAllGlobals())

const last: Meeting = {
  id: 7, date: '2026-11-16', title: '组会', minutes: '', agenda: [], files: [], created_by: { id: 3, name: '导师甲' },
  created_at: '', updated_at: '',
  actions: [
    { id: 70, owner: { id: 2, name: '学生甲' }, content: '补实验', due_date: '2026-11-20', done_at: null, carried_to: null },
    { id: 71, owner: { id: 2, name: '学生甲' }, content: '做完了', due_date: null, done_at: '2026-11-17T09:00:00+08:00', carried_to: null },
  ],
}

it('copies the open items of the latest meeting and sends where they came from', async () => {
  const calls: { url: string; method?: string; body?: unknown }[] = []
  vi.stubGlobal('fetch', vi.fn((url: string, init: RequestInit) => {
    calls.push({ url, method: init.method, body: init.body ? JSON.parse(init.body as string) : undefined })
    const page = (results: unknown[]) => ({ count: results.length, next: null, previous: null, results })
    const body = url.startsWith('/api/meetings/?') ? page([last]) : init.method === 'POST' ? { ...last, id: 8 } : page([])
    return Promise.resolve(new Response(JSON.stringify(body), { status: init.method === 'POST' ? 201 : 200 }))
  }))
  const pinia = createPinia()
  const stub = { template: '<div />' }
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/meetings', name: 'meetings', component: stub },
      { path: '/meetings/new', name: 'meeting-new', component: MeetingDetailView },
      { path: '/meetings/:id', name: 'meeting-detail', component: stub },
    ],
  })
  await router.push('/meetings/new')
  await router.isReady()
  useAuthStore(pinia).user = { id: 3, name: '导师甲', role: 'advisor', is_manager: false, is_supervisor: true } as Me
  const wrapper = mount(RouterView, { global: { plugins: [ElementPlus, pinia, router] }, attachTo: document.body })
  await flushPromises()
  const click = async (text: string) => {
    await wrapper.findAll('button').find((b) => b.text() === text)!.trigger('click')
    await flushPromises()
  }
  expect((wrapper.find('textarea').element as HTMLTextAreaElement).value).toContain('下周安排：')
  await click('带入上次未完成的事项')
  await click('带入上次未完成的事项') // twice: no duplicate rows
  await click('保存')
  const saved = calls.find((c) => c.method === 'POST' && c.url === '/api/meetings/')!.body as { actions: unknown[] }
  expect(saved.actions).toEqual([{ owner_id: 2, content: '补实验', due_date: '2026-11-20', carried_from: 70 }])
  wrapper.unmount()
})

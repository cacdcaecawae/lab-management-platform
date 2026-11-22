// Supervisor feedback on a submitted report: the "需补充 needs content" rule and the request body.
import { afterEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { createPinia } from 'pinia'
import { createMemoryHistory, createRouter, RouterView } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import type { Me, WeeklyReport } from '@/api/types'
import ReportEditView from './ReportEditView.vue'

afterEach(() => vi.unstubAllGlobals())

const report: WeeklyReport = {
  id: 8,
  owner: { id: 2, name: '陈同学' },
  week_start: '2026-11-16',
  status: 'submitted',
  submitted_at: '2026-11-20T18:00:00+08:00',
  goals: '完成标定',
  done: '采集 3 组数据',
  findings: '',
  next_plan: '',
  experiments: [{ id: 3, code: 'EX-2026-0003', title: '标定', status: 'submitted' }],
  datasets: [],
  runs: [],
  feedback: [],
  created_at: '2026-11-16T09:00:00+08:00',
  updated_at: '2026-11-20T18:00:00+08:00',
}

async function mountAsSupervisor(reportStatus = 200) {
  const fetchMock = vi.fn((url: string, init: RequestInit) => {
    let body: unknown = { count: 0, next: null, previous: null, results: [] }
    if (url === '/api/reports/8/' && reportStatus !== 200) return Promise.resolve(new Response('oops', { status: reportStatus }))
    if (url === '/api/reports/8/') body = report
    if (url === '/api/reports/8/feedback/') {
      const sent = JSON.parse(init.body as string)
      body = {
        ...report,
        status: sent.verdict,
        feedback: [{ id: 1, author: { id: 1, name: '王老师' }, created_at: '2026-11-21T09:00:00+08:00', ...sent }],
      }
    }
    return Promise.resolve(new Response(JSON.stringify(body), { status: 200 }))
  })
  vi.stubGlobal('fetch', fetchMock)

  const pinia = createPinia()
  const stub = { template: '<div />' }
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      ...['reports', 'experiment-edit', 'dataset-detail', 'run-edit'].map((name) => ({ path: `/${name}/:id?`, name, component: stub })),
      { path: '/r/:id', name: 'report-edit', component: ReportEditView },
    ],
  })
  await router.push('/r/8')
  await router.isReady()
  useAuthStore(pinia).user = { id: 1, name: '王老师', role: 'advisor', is_supervisor: true } as Me
  const wrapper = mount(RouterView, { global: { plugins: [ElementPlus, pinia, router] } })
  await flushPromises()
  return { wrapper, fetchMock }
}

const feedbackCalls = (m: ReturnType<typeof vi.fn>) => m.mock.calls.filter(([url]) => url === '/api/reports/8/feedback/')

describe('ReportEditView loading', () => {
  it('shows the error, not an empty create form, when the report fails to load', async () => {
    const { wrapper } = await mountAsSupervisor(500)
    expect(wrapper.text()).toContain('请求失败（500）')
    expect(wrapper.find('form').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('提交')
  })

  it('says 记录不存在或无权查看 on 404', async () => {
    const { wrapper } = await mountAsSupervisor(404)
    expect(wrapper.text()).toContain('记录不存在或无权查看')
  })
})

describe('ReportEditView feedback', () => {
  it('shows the report read-only with a feedback form', async () => {
    const { wrapper } = await mountAsSupervisor()
    expect(wrapper.text()).toContain('完成标定')
    expect(wrapper.text()).toContain('EX-2026-0003')
    expect(wrapper.text()).toContain('填写反馈')
    expect(wrapper.find('textarea').exists()).toBe(true) // only the feedback textarea; the report is not editable
    expect(wrapper.findAll('textarea')).toHaveLength(1)
  })

  it('requires content for 需补充 and posts verdict + content', async () => {
    const { wrapper, fetchMock } = await mountAsSupervisor()
    await wrapper.find('input[type="radio"][value="needs_revision"]').setValue(true)
    await wrapper.find('form').trigger('submit')
    expect(feedbackCalls(fetchMock)).toHaveLength(0)

    await wrapper.find('textarea').setValue('补充波形图')
    await wrapper.find('form').trigger('submit')
    await flushPromises()
    const calls = feedbackCalls(fetchMock)
    expect(calls).toHaveLength(1)
    expect(calls[0][1].method).toBe('POST')
    expect(JSON.parse(calls[0][1].body as string)).toEqual({ verdict: 'needs_revision', content: '补充波形图' })
    expect(wrapper.text()).toContain('需补充')
    expect(wrapper.text()).not.toContain('填写反馈') // no longer submitted
    expect(wrapper.text()).toContain('补充波形图')
  })
})

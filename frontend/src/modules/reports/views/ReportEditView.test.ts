// Supervisor feedback on a submitted report: the "需补充 needs content" rule and the request body.
import { afterEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus, { ElMessageBox } from 'element-plus'
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
  files: [],
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

it('carries the plan from exactly seven days earlier across New Year', async () => {
  const previous = { ...report, week_start: '2025-12-29', next_plan: '校准仪器' }
  const fetchMock = vi.fn(async (url: string) => {
    const query = new URL(url, 'http://localhost')
    const matches = query.pathname === '/api/reports/' && query.searchParams.get('owner') === '2'
      && query.searchParams.get('week_start') === previous.week_start
    return new Response(JSON.stringify({ results: matches ? [previous] : [] }))
  })
  vi.stubGlobal('fetch', fetchMock)
  const pinia = createPinia()
  useAuthStore(pinia).user = { id: 2, role: 'student' } as Me
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/reports/new', name: 'report-new', component: ReportEditView },
      { path: '/reports', name: 'reports', component: { template: '<div />' } },
    ],
  })
  await router.push('/reports/new?week_start=2026-01-05')
  const wrapper = mount(ReportEditView, { global: { plugins: [ElementPlus, pinia, router] } })
  await wrapper.findAll('button').find((b) => b.text() === '带入上周计划')!.trigger('click')
  await flushPromises()
  expect(wrapper.get('textarea').element.value).toBe('校准仪器')
  wrapper.unmount()
})

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

  it('offers 下一份待反馈 after feedback when another submitted report exists', async () => {
    const fetchMock = vi.fn((url: string, init?: RequestInit) => {
      let body: unknown = { count: 0, next: null, previous: null, results: [] }
      if (url === '/api/reports/8/') body = report
      if (url === '/api/reports/8/feedback/') {
        const sent = JSON.parse(init!.body as string)
        body = {
          ...report,
          status: sent.verdict,
          feedback: [{ id: 1, author: { id: 1, name: '王老师' }, created_at: '2026-11-21T09:00:00+08:00', ...sent }],
        }
      }
      if (url.startsWith('/api/reports/?status=submitted')) {
        body = {
          count: 1,
          next: null,
          previous: null,
          results: [{ id: 9, owner: { id: 3, name: '李同学' }, week_start: '2026-11-16', status: 'submitted', submitted_at: '2026-11-20T19:00:00+08:00' }],
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

    await wrapper.find('form').trigger('submit')
    await flushPromises()
    expect(wrapper.text()).toContain('下一份待反馈')
  })
})

describe('ReportEditView owner tools', () => {
  async function mountAsOwner(start: string, respond: (url: string, init?: RequestInit) => unknown) {
    const page = { count: 0, next: null, previous: null, results: [] }
    const fetchMock = vi.fn(async (url: string, init?: RequestInit) =>
      new Response(JSON.stringify(respond(url, init) ?? page), { status: 200 }))
    vi.stubGlobal('fetch', fetchMock)
    const pinia = createPinia()
    const stub = { template: '<div />' }
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [
        ...['reports', 'experiment-edit', 'dataset-detail', 'run-edit'].map((name) => ({ path: `/${name}/:id?`, name, component: stub })),
        { path: '/reports/new', name: 'report-new', component: ReportEditView },
        { path: '/r/:id', name: 'report-edit', component: ReportEditView },
      ],
    })
    await router.push(start)
    await router.isReady()
    useAuthStore(pinia).user = { id: 2, name: '陈同学', role: 'student' } as Me
    const wrapper = mount(RouterView, { global: { plugins: [ElementPlus, pinia, router] } })
    await flushPromises()
    const click = async (text: string) => {
      await wrapper.findAll('button').find((b) => b.text() === text)!.trigger('click')
      await flushPromises()
    }
    return { wrapper, fetchMock, click }
  }

  it('ticks the week’s own records with 一键带入本周记录', async () => {
    const week = {
      experiments: [{ id: 5, code: 'EX-2026-0005', title: '重复性', status: 'draft' }],
      runs: [{ id: 6, code: 'RUN-2026-0006', title: '包络提取', status: 'submitted' }],
    }
    const { wrapper, fetchMock, click } = await mountAsOwner('/reports/new?week_start=2026-11-16', (url, init) => {
      if (url === '/api/reports/week-records/?week_start=2026-11-16') return week
      if (url === '/api/reports/' && init?.method === 'POST') return { ...report, status: 'draft', ...JSON.parse(init.body as string) }
    })
    await click('一键带入本周记录')
    await click('一键带入本周记录') // twice: nothing is ticked twice
    expect(wrapper.text()).toContain('EX-2026-0005 重复性')
    await click('保存草稿')
    const post = fetchMock.mock.calls.find(([url, init]) => url === '/api/reports/' && init?.method === 'POST')!
    const body = JSON.parse(post[1]!.body as string)
    expect([body.experiment_ids, body.run_ids, body.dataset_ids]).toEqual([[5], [6], []])
    wrapper.unmount()
  })

  it('takes a submitted report back to edit it', async () => {
    const confirm = vi.spyOn(ElMessageBox, 'confirm').mockResolvedValue('confirm' as never)
    const mine = { ...report, owner: { id: 2, name: '陈同学' } }
    const { wrapper, fetchMock, click } = await mountAsOwner('/r/8', (url) => {
      if (url === '/api/reports/8/') return mine
      if (url === '/api/reports/8/withdraw/') return { ...mine, status: 'draft', submitted_at: null }
    })
    expect(wrapper.find('form').exists()).toBe(false) // submitted: read-only
    await click('撤回修改')
    expect(confirm).toHaveBeenCalled()
    expect(fetchMock.mock.calls.some(([url, init]) => url === '/api/reports/8/withdraw/' && init?.method === 'POST')).toBe(true)
    expect(wrapper.find('form').exists()).toBe(true)
    expect(wrapper.text()).not.toContain('撤回修改')
    confirm.mockRestore()
    wrapper.unmount()
  })
})

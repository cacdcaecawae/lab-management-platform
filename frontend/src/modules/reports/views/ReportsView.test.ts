import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { createPinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import type { Me, UserBrief, WeeklyReportDigest } from '@/api/types'
import ReportsView from './ReportsView.vue'

interface Deferred<T> {
  promise: Promise<T>
  resolve: (value: T) => void
  reject: (err: unknown) => void
}

function deferred<T>(): Deferred<T> {
  let resolve!: (value: T) => void
  let reject!: (err: unknown) => void
  const promise = new Promise<T>((res, rej) => {
    resolve = res
    reject = rej
  })
  return { promise, resolve, reject }
}

function makeDigest(week_start: string, ownerName: string, done: string, missingName: string): WeeklyReportDigest {
  return {
    week_start,
    reports: [
      {
        id: week_start === '2026-11-16' ? 101 : 102,
        owner: { id: 2, name: ownerName },
        week_start,
        status: 'submitted',
        submitted_at: `${week_start}T18:00:00+08:00`,
        goals: '',
        done,
        findings: '',
        next_plan: '',
        experiments: [],
        datasets: [],
        runs: [],
        feedback: [],
        files: [],
        created_at: `${week_start}T09:00:00+08:00`,
        updated_at: `${week_start}T18:00:00+08:00`,
      },
    ],
    missing: [{ id: 3, name: missingName }],
  }
}

beforeEach(() => {
  vi.clearAllMocks()
})

afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

async function mountSupervisor(fetchImpl: (url: string, init?: RequestInit) => Promise<Response>) {
  vi.stubGlobal('fetch', vi.fn(fetchImpl))
  const pinia = createPinia()
  const stub = { template: '<div />' }
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/reports', name: 'reports', component: ReportsView },
      ...['report-new', 'report-edit', 'experiment-edit', 'dataset-detail', 'run-edit'].map((name) => ({
        path: `/${name}/:id?`,
        name,
        component: stub,
      })),
    ],
  })
  await router.push('/reports')
  await router.isReady()
  useAuthStore(pinia).user = { id: 1, name: '王老师', role: 'advisor', is_supervisor: true } as Me
  const wrapper = mount(ReportsView, { global: { plugins: [ElementPlus, pinia, router] } })
  await flushPromises()
  return wrapper
}

describe('ReportsView rapid week switching', () => {
  it('only reports everyone submitted after a successful empty response', async () => {
    let attempts = 0
    const wrapper = await mountSupervisor(async (url) => {
      if (url.startsWith('/api/reports/missing/')) {
        return ++attempts === 1 ? new Response('{}', { status: 500 }) : new Response('[]')
      }
      return new Response(JSON.stringify({ count: 0, results: [] }))
    })
    await wrapper.findAll('.el-tabs__item').find((t) => t.text() === '未交名单')!.trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('未交名单加载失败')
    expect(wrapper.text()).not.toContain('这一周没有未交的同学')
    await wrapper.findAll('button').find((b) => b.text() === '重试')!.trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('这一周没有未交的同学')
    wrapper.unmount()
  })

  it('aborts older digest request and ignores late out-of-order response', async () => {
    const calls: Array<{ url: string; signal?: AbortSignal; d: Deferred<Response> }> = []
    const wrapper = await mountSupervisor((url, init) => {
      if (url.startsWith('/api/reports/digest/')) {
        const d = deferred<Response>()
        calls.push({ url, signal: init?.signal ?? undefined, d })
        return d.promise
      }
      return Promise.resolve(new Response(JSON.stringify({ count: 0, next: null, previous: null, results: [] }), { status: 200 }))
    })

    // Switch to 本周汇总 tab -> triggers first digest request (initial week)
    const digestTab = wrapper.findAll('.el-tabs__item').find((t) => t.text() === '本周汇总')!
    await digestTab.trigger('click')
    await flushPromises()
    expect(calls).toHaveLength(1)
    expect(calls[0]!.signal?.aborted).toBe(false)

    // Quickly switch to an earlier week, then another week before first resolves
    const picker = wrapper.findComponent({ name: 'ElDatePicker' })
    picker.vm.$emit('update:modelValue', '2026-11-09')
    await flushPromises()
    expect(calls).toHaveLength(2)
    expect(calls[0]!.signal?.aborted).toBe(true)
    expect(calls[1]!.url).toContain('week_start=2026-11-09')

    picker.vm.$emit('update:modelValue', '2026-11-16')
    await flushPromises()
    expect(calls).toHaveLength(3)
    expect(calls[1]!.signal?.aborted).toBe(true)
    expect(calls[2]!.url).toContain('week_start=2026-11-16')

    // Latest week (2026-11-16) arrives first
    calls[2]!.d.resolve(
      new Response(JSON.stringify(makeDigest('2026-11-16', '本周同学', '本周完成工作', '本周未交')), { status: 200 }),
    )
    await flushPromises()
    expect(wrapper.text()).toContain('本周完成工作')
    expect(wrapper.text()).toContain('本周未交')

    // Older week (2026-11-09) arrives late (simulating a response that resolved despite abort)
    calls[1]!.d.resolve(
      new Response(JSON.stringify(makeDigest('2026-11-09', '上周同学', '上周旧数据', '上周未交')), { status: 200 }),
    )
    await flushPromises()

    // Must still display 2026-11-16, never overwritten by stale 2026-11-09
    expect(wrapper.text()).toContain('本周完成工作')
    expect(wrapper.text()).toContain('本周未交')
    expect(wrapper.text()).not.toContain('上周旧数据')
    expect(wrapper.text()).not.toContain('上周未交')
    wrapper.unmount()
  })

  it('aborts older missing-list request and ignores late out-of-order response', async () => {
    const calls: Array<{ url: string; signal?: AbortSignal; d: Deferred<Response> }> = []
    const wrapper = await mountSupervisor((url, init) => {
      if (url.startsWith('/api/reports/missing/')) {
        const d = deferred<Response>()
        calls.push({ url, signal: init?.signal ?? undefined, d })
        return d.promise
      }
      return Promise.resolve(new Response(JSON.stringify({ count: 0, next: null, previous: null, results: [] }), { status: 200 }))
    })

    const missingTab = wrapper.findAll('.el-tabs__item').find((t) => t.text() === '未交名单')!
    await missingTab.trigger('click')
    await flushPromises()
    expect(calls).toHaveLength(1)

    const picker = wrapper.findComponent({ name: 'ElDatePicker' })
    picker.vm.$emit('update:modelValue', '2026-11-09')
    await flushPromises()
    picker.vm.$emit('update:modelValue', '2026-11-16')
    await flushPromises()
    expect(calls).toHaveLength(3)
    expect(calls[0]!.signal?.aborted).toBe(true)
    expect(calls[1]!.signal?.aborted).toBe(true)

    const currentMissing: UserBrief[] = [{ id: 10, name: '本周未交甲' }]
    const staleMissing: UserBrief[] = [{ id: 11, name: '上周未交乙' }]

    calls[2]!.d.resolve(new Response(JSON.stringify(currentMissing), { status: 200 }))
    await flushPromises()
    expect(wrapper.text()).toContain('本周未交甲')

    calls[1]!.d.resolve(new Response(JSON.stringify(staleMissing), { status: 200 }))
    await flushPromises()
    expect(wrapper.text()).toContain('本周未交甲')
    expect(wrapper.text()).not.toContain('上周未交乙')
    wrapper.unmount()
  })
})

describe('ReportsView 本周汇总 quick review', () => {
  async function openDigest(sent: unknown[]) {
    const digest = makeDigest('2026-11-16', '陈同学', '采集 3 组数据', '李同学')
    const wrapper = await mountSupervisor(async (url, init) => {
      if (url.startsWith('/api/reports/digest/')) return new Response(JSON.stringify(digest))
      if (url === '/api/reports/101/feedback/') {
        const body = JSON.parse(init!.body as string)
        sent.push(body)
        return new Response(JSON.stringify({ ...digest.reports[0], status: body.verdict }))
      }
      return new Response(JSON.stringify({ count: 0, next: null, previous: null, results: [] }))
    })
    await wrapper.findAll('.el-tabs__item').find((t) => t.text() === '本周汇总')!.trigger('click')
    await flushPromises()
    const click = async (text: string) => {
      await wrapper.findAll('button').find((b) => b.text() === text)!.trigger('click')
      await flushPromises()
    }
    return { wrapper, click }
  }

  it('sends 已阅 without a comment from 一键已阅', async () => {
    const sent: unknown[] = []
    const { wrapper, click } = await openDigest(sent)
    await click('一键已阅')
    expect(sent).toEqual([{ verdict: 'reviewed', content: '' }])
    expect(wrapper.text()).not.toContain('一键已阅') // no longer waiting for feedback
    expect(wrapper.text()).toContain('查看详情')
    wrapper.unmount()
  })

  it('wants a comment for 需补充', async () => {
    const sent: unknown[] = []
    const { wrapper, click } = await openDigest(sent)
    await click('写评语')
    await click('需补充')
    expect(sent).toHaveLength(0)
    await wrapper.find('.digest-comment textarea').setValue('补充波形图')
    await click('需补充')
    expect(sent).toEqual([{ verdict: 'needs_revision', content: '补充波形图' }])
    wrapper.unmount()
  })
})

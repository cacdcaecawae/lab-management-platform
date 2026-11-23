// A review is a decision about what is on screen: it carries the submission, status and total the reviewer saw,
// and a 409 `stale` (the request changed meanwhile) reloads the page instead of being reported as an error.
import { afterEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { createPinia } from 'pinia'
import { createMemoryHistory, createRouter, RouterView } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import type { Me, PurchaseDetail } from '@/api/types'
import PurchaseDetailView from './PurchaseDetailView.vue'

afterEach(() => vi.unstubAllGlobals())

const purchase: PurchaseDetail = {
  id: 5,
  code: 'PR-2026-0005',
  owner: { id: 2, name: '陈同学' },
  purpose: '搭建相控阵实验台',
  status: 'pending_initial',
  fund: { id: 1, code: 'NSFC-001', name: '国自然面上', active: true },
  items: [{ id: 1, name: '5MHz 探头', spec: 'Φ10', quantity: 2, unit_price: '1200.00', subtotal: '2400.00', link: '' }],
  total: '2400.00',
  returned: false,
  submitted_at: '2026-11-17T09:00:00.123456+08:00',
  created_at: '2026-11-17T08:00:00+08:00',
  updated_at: '2026-11-17T09:00:00+08:00',
  approvals: [],
  attachments: [],
  linked_equipment: [],
  linked_stock: [],
}

async function mountAsManager(reviewResponse: { status: number; body: unknown }, refreshed = purchase) {
  const calls: { url: string; body?: unknown }[] = []
  const fetchMock = vi.fn((url: string, init: RequestInit) => {
    calls.push({ url, body: init.body ? JSON.parse(init.body as string) : undefined })
    if (url === '/api/purchases/5/review/') {
      return Promise.resolve(new Response(JSON.stringify(reviewResponse.body), { status: reviewResponse.status }))
    }
    const detail = calls.filter((c) => c.url === '/api/purchases/5/').length > 1 ? refreshed : purchase
    const body = url === '/api/purchases/5/' ? detail : { count: 0, next: null, previous: null, results: [] }
    return Promise.resolve(new Response(JSON.stringify(body), { status: 200 }))
  })
  vi.stubGlobal('fetch', fetchMock)

  const pinia = createPinia()
  const stub = { template: '<div />' }
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      ...['purchases', 'purchase-reviews', 'equipment-detail'].map((name) => ({ path: `/${name}/:id?`, name, component: stub })),
      { path: '/p/:id', name: 'purchase-detail', component: PurchaseDetailView },
    ],
  })
  await router.push('/p/5')
  await router.isReady()
  useAuthStore(pinia).user = { id: 1, name: '管理员', role: 'manager', is_supervisor: true } as Me
  const wrapper = mount(RouterView, { global: { plugins: [ElementPlus, pinia, router] }, attachTo: document.body })
  await flushPromises()
  const click = async (text: string) => {
    await wrapper.findAll('button').find((b) => b.text() === text)!.trigger('click')
    await flushPromises()
  }
  return { wrapper, calls, click }
}

describe('PurchaseDetailView review', () => {
  it('sends the submission, status and total on screen', async () => {
    const { calls, click } = await mountAsManager({ status: 200, body: { ...purchase, status: 'pending_final' } })
    await click('通过')
    expect(calls.find((c) => c.url === '/api/purchases/5/review/')?.body).toEqual({
      verdict: 'approve', comment: '', status_seen: 'pending_initial', total_seen: '2400.00',
      submitted_seen: purchase.submitted_at,
    })
  })

  it('needs a comment to send back, without a request', async () => {
    const { wrapper, calls, click } = await mountAsManager({ status: 200, body: purchase })
    await click('退回修改')
    expect(calls.some((c) => c.url === '/api/purchases/5/review/')).toBe(false)
    expect(wrapper.text()).toContain('退回时请写明意见')
  })

  it('reloads when the request changed meanwhile', async () => {
    const stale = { code: 'stale', message: '单据已变化（状态或金额与你看到的不同），请刷新后再审' }
    const refreshed = { ...purchase, submitted_at: '2026-11-18T09:00:00+08:00' }
    const { calls, click } = await mountAsManager({ status: 409, body: stale }, refreshed)
    const loads = () => calls.filter((c) => c.url === '/api/purchases/5/').length
    expect(loads()).toBe(1)
    await click('通过')
    expect(loads()).toBe(2)
    await click('通过')
    expect(calls.filter((c) => c.url === '/api/purchases/5/review/').map((c) => c.body)).toEqual([
      expect.objectContaining({ submitted_seen: purchase.submitted_at }),
      expect.objectContaining({ submitted_seen: refreshed.submitted_at }),
    ])
  })
})

describe('PurchaseDetailView items', () => {
  it('shows a row error under its own row when a blank row before it is not sent', async () => {
    const draft = { ...purchase, status: 'draft', submitted_at: null, items: [], total: '0.00' } as PurchaseDetail
    const sent: unknown[] = []
    vi.stubGlobal('fetch', vi.fn((url: string, init: RequestInit) => {
      if (init.method === 'PATCH') {
        sent.push(JSON.parse(init.body as string))
        const errors = { items: [{ unit_price: ['请填写单价'] }] } // numbered by the items the server got
        return Promise.resolve(new Response(JSON.stringify({ code: 'validation_error', message: '提交的数据有误', errors }), { status: 400 }))
      }
      const body = url === '/api/purchases/5/' ? draft : { count: 0, next: null, previous: null, results: [] }
      return Promise.resolve(new Response(JSON.stringify(body), { status: 200 }))
    }))
    const pinia = createPinia()
    const stub = { template: '<div />' }
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [
        ...['purchases', 'purchase-reviews', 'equipment-detail'].map((name) => ({ path: `/${name}/:id?`, name, component: stub })),
        { path: '/p/:id', name: 'purchase-detail', component: PurchaseDetailView },
      ],
    })
    await router.push('/p/5')
    await router.isReady()
    useAuthStore(pinia).user = { id: 2, name: '陈同学', role: 'student', is_supervisor: false } as Me // the applicant
    const wrapper = mount(RouterView, { global: { plugins: [ElementPlus, pinia, router] }, attachTo: document.body })
    await flushPromises()
    const click = async (text: string) => {
      await wrapper.findAll('button').find((b) => b.text() === text)!.trigger('click')
      await flushPromises()
    }

    await click('添加一行') // row 1 stays blank, row 2 gets a name but no price
    await wrapper.findAll('input[aria-label="品名"]')[1].setValue('探头支架')
    await click('保存草稿')

    expect(sent).toEqual([expect.objectContaining({ items: [expect.objectContaining({ name: '探头支架' })] })])
    const error = wrapper.get('.row-error')
    expect(error.text()).toBe('单价：请填写单价')
    expect(error.element.previousElementSibling!.querySelector<HTMLInputElement>('input[aria-label="品名"]')!.value).toBe('探头支架')
    wrapper.unmount()
  })
})

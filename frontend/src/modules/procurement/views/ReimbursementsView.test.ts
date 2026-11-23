// 交财务 in the dialog hands in what is on screen: an edit not saved yet goes in first (afterwards nothing can change).
import { afterEach, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { createPinia } from 'pinia'
import { useAuthStore } from '@/stores/auth'
import type { Me, Reimbursement } from '@/api/types'
import ReimbursementsView from './ReimbursementsView.vue'

vi.mock('element-plus', async (original) => ({
  ...(await original<typeof import('element-plus')>()),
  ElMessageBox: { confirm: vi.fn().mockResolvedValue('confirm') },
}))
afterEach(() => vi.unstubAllGlobals())

const me = { id: 1, name: '陈同学' }
const record = {
  id: 7,
  code: 'RB-2026-0007',
  owner: me,
  fund: { id: 1, code: 'NSFC-001', name: '国自然面上', active: true },
  purchase: null,
  category: 'consumable',
  amount: '120.00',
  occurred_on: '2026-11-20',
  description: '耦合剂',
  status: 'pending',
  submitted_at: null,
  paid_at: null,
  attachments: [{ id: 3, kind: 'invoice', name: '发票.pdf', size: 10, uploaded_by: me, url: '/api/attachments/3/file/', created_at: '2026-11-20T10:00:00+08:00' }],
  created_at: '2026-11-20T10:00:00+08:00',
  updated_at: '2026-11-20T10:00:00+08:00',
} as Reimbursement

it('交财务 saves an edit made in the dialog before handing it in', async () => {
  const sent: string[] = []
  vi.stubGlobal('fetch', vi.fn((url: string, init: RequestInit) => {
    if (init.method && init.method !== 'GET') sent.push(`${init.method} ${url} ${init.body}`)
    const body = url.endsWith('/advance/')
      ? { ...record, status: 'submitted' }
      : init.method === 'PATCH'
        ? { ...record, description: '耦合剂 3 瓶' }
        : { count: url.startsWith('/api/reimbursements/') ? 1 : 0, next: null, previous: null, results: url.startsWith('/api/reimbursements/') ? [record] : [] }
    return Promise.resolve(new Response(JSON.stringify(body), { status: 200 }))
  }))
  const pinia = createPinia()
  useAuthStore(pinia).user = { ...me, role: 'student', is_supervisor: false } as Me
  const wrapper = mount(ReimbursementsView, { global: { plugins: [ElementPlus, pinia] }, attachTo: document.body })
  await flushPromises()
  await wrapper.findAll('button').find((b) => b.text() === record.code)!.trigger('click')
  await flushPromises()

  const description = document.querySelector<HTMLInputElement>('input[placeholder="如 耦合剂 3 瓶、会议差旅"]')!
  description.value = '耦合剂 3 瓶'
  description.dispatchEvent(new Event('input'))
  await flushPromises()
  const handIn = [...document.querySelectorAll('.el-dialog button')].find((b) => b.textContent?.trim() === '交财务') as HTMLButtonElement
  expect(handIn.classList.contains('el-button--primary')).toBe(false) // 保存 is the dialog's one main button
  handIn.click()
  await flushPromises()

  expect(sent).toEqual([
    'PATCH /api/reimbursements/7/ {"description":"耦合剂 3 瓶"}',
    'POST /api/reimbursements/7/advance/ {"status":"submitted"}',
  ])
  wrapper.unmount()
})

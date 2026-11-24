import { afterEach, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { createPinia } from 'pinia'
import { useAuthStore } from '@/stores/auth'
import type { Consumable, Me } from '@/api/types'
import ConsumablesView from './ConsumablesView.vue'

afterEach(() => {
  vi.unstubAllGlobals()
  document.body.innerHTML = ''
})

it('defaults issue to earliest eligible positive batch, not expired or zero-balance rows', async () => {
  const item: Consumable = { id: 1, name: '耦合剂', spec: '', unit: '瓶', category: '', location: '', safety_stock: 0,
    stock: 10, stock_version: 7, low: false, notes: '', created_at: '', updated_at: '', tracks_batches: true,
    batches: [
      { id: 1, batch_no: '过期批次', expires_on: '2024-01-01', stock: 2, can_issue: false },
      { id: 2, batch_no: '空批次', expires_on: '2030-01-01', stock: 0, can_issue: false },
      { id: 3, batch_no: '最先到期且有库存', expires_on: '2030-02-01', stock: 4, can_issue: true },
      { id: 4, batch_no: '第二个可用批次', expires_on: null, stock: 4, can_issue: true },
    ],
  }
  let submitted: Record<string, unknown> | null = null
  vi.stubGlobal('fetch', vi.fn((url: string, init: RequestInit) => {
    if (url === '/api/consumables/1/txns/') {
      submitted = JSON.parse(init.body as string)
      return Promise.resolve(new Response(JSON.stringify({ id: 11 }), { status: 201 }))
    }
    const contains = url.startsWith('/api/consumables/?')
    return Promise.resolve(new Response(JSON.stringify({ count: contains ? 1 : 0, next: null,
      previous: null, results: contains ? [item] : [] }), { status: 200 }))
  }))
  const pinia = createPinia()
  useAuthStore(pinia).user = { id: 2, name: '学生甲', role: 'student' } as Me
  const wrapper = mount(ConsumablesView, { global: { plugins: [ElementPlus, pinia] }, attachTo: document.body })
  try {
    await flushPromises()
    await wrapper.findAll('button').find((button) => button.text() === '领用')!.trigger('click')
    await flushPromises()
    expect(document.body.querySelector('.el-dialog')?.textContent).toContain('该批次 4 瓶')
    const submit = Array.from(document.body.querySelectorAll('.el-dialog button')).find((b) => b.textContent?.trim() === '登记')
    submit!.dispatchEvent(new MouseEvent('click', { bubbles: true }))
    await flushPromises()
    expect(submitted).toMatchObject({ kind: 'out', batch_id: 3 })
  } finally {
    wrapper.unmount()
  }
})

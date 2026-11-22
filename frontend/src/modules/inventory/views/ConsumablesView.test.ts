import { afterEach, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { createPinia } from 'pinia'
import { useAuthStore } from '@/stores/auth'
import type { Consumable, Me } from '@/api/types'
import ConsumablesView from './ConsumablesView.vue'

afterEach(() => { vi.unstubAllGlobals(); document.body.innerHTML = '' })

it('sends the displayed ledger version and reloads without retrying a stale stocktake', async () => {
  const item: Consumable = { id: 1, name: '线缆', spec: '', unit: '根', location: '', safety_stock: 0,
    stock: 10, stock_version: 7, low: false, notes: '', created_at: '', updated_at: '' }
  const calls: { url: string; body?: unknown }[] = []
  vi.stubGlobal('fetch', vi.fn((url: string, init: RequestInit) => {
    calls.push({ url, body: init.body ? JSON.parse(init.body as string) : undefined })
    if (url === '/api/consumables/1/txns/') return Promise.resolve(new Response(JSON.stringify({
      code: 'stale_stock', message: 'changed',
    }), { status: 409 }))
    const isItems = url.startsWith('/api/consumables/?')
    return Promise.resolve(new Response(JSON.stringify({ count: isItems ? 1 : 0, next: null,
      previous: null, results: isItems ? [item] : [] }), { status: 200 }))
  }))
  const pinia = createPinia()
  useAuthStore(pinia).user = { id: 1, name: '管理员', role: 'manager', is_supervisor: true } as Me
  const wrapper = mount(ConsumablesView, { global: { plugins: [ElementPlus, pinia] }, attachTo: document.body })
  await flushPromises()
  // 盘点 sits in the row's "更多" menu
  await wrapper.findAll('button').filter((b) => b.text() === '更多').at(-1)!.trigger('click')
  await flushPromises()
  ;(Array.from(document.querySelectorAll('.el-dropdown-menu__item')).find((i) => i.textContent?.trim() === '盘点') as HTMLElement).click()
  await flushPromises()
  const input = document.querySelector('.el-dialog input[role="spinbutton"]') as HTMLInputElement
  input.value = '8'
  input.dispatchEvent(new Event('input', { bubbles: true }))
  input.dispatchEvent(new Event('change', { bubbles: true }))
  await flushPromises()
  const submit = Array.from(document.querySelectorAll('.el-dialog button')).find((b) => b.textContent?.trim() === '登记') as HTMLButtonElement
  expect(submit.disabled).toBe(false)
  submit.click()
  await flushPromises()
  const writes = calls.filter((c) => c.url === '/api/consumables/1/txns/')
  expect(writes).toHaveLength(1)
  expect(writes[0]!.body).toEqual(expect.objectContaining({ kind: 'adjust', quantity: -2, stock_version_seen: 7 }))
  expect(calls.filter((c) => c.url.startsWith('/api/consumables/?'))).toHaveLength(2)
  expect(document.body.textContent).toContain('请重新打开盘点并核对实际数量')
  wrapper.unmount()
})

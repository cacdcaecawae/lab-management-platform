// @vitest-environment jsdom
import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { expect, it, vi } from 'vitest'
import SystemLoginEvents from './SystemLoginEvents.vue'

const audit = vi.hoisted(() => ({ list: vi.fn() }))
vi.mock('@/api/loginEvents', () => ({ loginEventsApi: audit }))

it('shows structured outcomes and applies a trimmed known-account filter', async () => {
  audit.list.mockResolvedValue({
    count: 2, next: null, previous: null,
    audit_enabled: true,
    results: [
      { id: 2, at: '2026-11-19T08:00:00Z', outcome: 'throttled', account: null, ip: null },
      { id: 1, at: '2026-11-19T07:59:32Z', outcome: 'failed', account: { id: 7, username: 'synthetic' }, ip: '192.0.2.1' },
    ],
    top_failed_24h: [{ user_id: 7, user__username: 'synthetic', failures: 2 }],
  })
  const page = mount(SystemLoginEvents, { global: { plugins: [ElementPlus] } })
  await flushPromises()
  expect(page.text()).toContain('未归属')
  expect(page.text()).toContain('限流发生分钟')
  expect(page.text()).toContain('synthetic：2 次')
  await page.get('input[aria-label="登录名"]').setValue(' synthetic ')
  await page.get('form').trigger('submit')
  await flushPromises()
  expect(audit.list).toHaveBeenLastCalledWith({ username: 'synthetic', outcome: '', from: '', to: '', page: 1 })
  page.unmount()
})

// @vitest-environment jsdom
import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import EquipmentStatsView from './EquipmentStatsView.vue'

const api = vi.hoisted(() => ({
  list: vi.fn(),
  exportUrl: vi.fn((q: { from: string; to: string; by: string }) => `/export?from=${q.from}&to=${q.to}&by=${q.by}`),
}))
vi.mock('../api', () => ({ usageStatsApi: api }))

beforeEach(() => {
  vi.useFakeTimers({ toFake: ['Date'] }).setSystemTime(new Date('2026-11-30T16:00:00Z'))
  api.list.mockResolvedValue([{ key: { id: 1, label: 'A 校验' }, booked_hours: 5, reported_hours: 3, bookings: 3, abnormal: 1 }])
})
afterEach(() => { vi.useRealTimers(); vi.clearAllMocks() })

it('loads the Shanghai month and exports the displayed query', async () => {
  const page = mount(EquipmentStatsView, { global: { plugins: [ElementPlus] } })
  await flushPromises()
  expect(api.list).toHaveBeenCalledWith({ from: '2026-12-01', to: '2027-01-01', by: 'equipment' })
  expect(page.text()).toContain('A 校验')
  expect(page.text()).toContain('5.00')
  expect(page.text()).toContain('预约小时不是实际使用时长')
  expect(page.get('a').attributes('href')).toBe('/export?from=2026-12-01&to=2027-01-01&by=equipment')
  page.unmount()
})

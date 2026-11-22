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
  expect(page.text()).not.toContain('预约小时不是实际使用时长') // the counting rules live in docs, not on screen
  expect(page.get('a').attributes('href')).toBe('/export?from=2026-12-01&to=2027-01-01&by=equipment')
  page.unmount()
})

it('applies a changed grouping at once and keeps the newest answer', async () => {
  let slow!: (rows: unknown[]) => void
  api.list.mockImplementationOnce(() => new Promise((resolve) => { slow = resolve }))
  api.list.mockResolvedValueOnce([{ key: { id: 7, label: '学生甲' }, booked_hours: 1, reported_hours: 0, bookings: 1, abnormal: 0 }])
  const page = mount(EquipmentStatsView, { global: { plugins: [ElementPlus] } })
  const select = page.findComponent({ name: 'ElSelect' })
  select.vm.$emit('update:modelValue', 'user')
  select.vm.$emit('change', 'user') // no 查询 button: the toolbar applies on change
  await flushPromises()
  expect(api.list).toHaveBeenLastCalledWith({ from: '2026-12-01', to: '2027-01-01', by: 'user' })
  slow([{ key: { id: 1, label: 'A 校验' }, booked_hours: 5, reported_hours: 3, bookings: 3, abnormal: 1 }])
  await flushPromises()
  expect(page.text()).toContain('学生甲')
  expect(page.text()).not.toContain('A 校验') // the first, slower answer arrived last and is dropped
  expect(page.get('a').attributes('href')).toBe('/export?from=2026-12-01&to=2027-01-01&by=user')
  page.unmount()
})

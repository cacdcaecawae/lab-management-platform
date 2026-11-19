import { afterEach, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { createPinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'
import type { Dashboard } from '@/api/types'
import EquipmentView from '@/modules/equipment/views/EquipmentView.vue'
import SpecimensView from '@/modules/specimens/views/SpecimensView.vue'
import WorkbenchView from './WorkbenchView.vue'

afterEach(() => vi.unstubAllGlobals())

const loan = {
  loan_id: 42,
  specimen: { id: 7, code: 'S-7', name: '试件甲', status: 'available' as const },
  borrowed_at: '2026-11-18T12:00:00Z',
  due_date: '2026-11-19',
  overdue: true,
}
const base: Dashboard = {
  my: {
    borrowed_specimens: [loan], borrowed_specimens_count: 21,
    action_items: [], reports_needing_revision: [], draft_experiments: [],
    current_week_report: null, upcoming_bookings: [], unreported_bookings: [], returned_purchases: [],
  },
  supervisor: null,
  manager: null,
}
const names = {
  workbench: '/', specimens: '/specimens', 'specimen-detail': '/specimens/:id',
  equipment: '/equipment', 'equipment-detail': '/equipment/:id', 'report-new': '/reports/new',
  reports: '/reports', experiments: '/experiments', bookings: '/bookings', consumables: '/consumables',
}

async function setup(path: string, data = base) {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: Object.entries(names).map(([name, path]) => ({ name, path, component: { template: '<div />' } })),
  })
  await router.push(path)
  const fetch = vi.fn((url: string) => Promise.resolve(new Response(JSON.stringify(
    url === '/api/dashboard/' ? data : { results: [], count: 0, next: null, previous: null },
  ), { status: 200 })))
  vi.stubGlobal('fetch', fetch)
  return { fetch, global: { plugins: [ElementPlus, createPinia(), router] } }
}

it('shows actual totals and links each reminder to its matching filter', async () => {
  const { global } = await setup('/', {
    ...base,
    manager: {
      equipment_to_check: [], low_stock: [],
      overdue_loans: [{ ...loan, borrower: { id: 1, name: '学生甲' } }], overdue_loans_count: 22,
      calibration_due: [{ id: 1, code: 'E-1', name: '设备甲', status: 'available', calibration_due: '2026-11-19' }],
      calibration_due_count: 23,
    },
  })
  const wrapper = mount(WorkbenchView, { global })
  await flushPromises()
  const tile = (href: string) => wrapper.get(`a[href="${href}"]`).text()
  expect(tile('/specimens?mine=1')).toContain('21')
  expect(tile('/specimens?overdue=1')).toContain('22')
  expect(tile('/equipment?calibration_within=30')).toContain('23')
  expect(wrapper.text()).toContain('已逾期')
  expect(wrapper.text()).toContain('学生甲')
  wrapper.unmount()
})

it.each([
  ['/specimens?mine=1', SpecimensView, '/api/specimens/', 'mine', '1'],
  ['/specimens?overdue=1', SpecimensView, '/api/specimens/', 'overdue', '1'],
  ['/equipment?calibration_within=30', EquipmentView, '/api/equipment/', 'calibration_within', '30'],
] as const)('initializes its filter from %s', async (path, view, endpoint, key, value) => {
  const { global, fetch } = await setup(path)
  const wrapper = mount(view, { global })
  await flushPromises()
  const url = new URL(fetch.mock.calls.find(([url]) => url.startsWith(endpoint))![0], 'https://example.test')
  expect(url.searchParams.get(key)).toBe(value)
  wrapper.unmount()
})

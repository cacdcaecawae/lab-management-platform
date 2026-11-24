import { afterEach, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { createPinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'
import type { Dashboard, Me } from '@/api/types'
import { useAuthStore } from '@/stores/auth'
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
    tasks: [], action_items: [], reports_needing_revision: [], draft_experiments: [],
    current_week_report: null, upcoming_bookings: [], unreported_bookings: [], returned_purchases: [],
    draft_runs: [], draft_purchases: [], reimbursements_without_invoice: [],
  },
  supervisor: null,
  manager: null,
}
const names = {
  workbench: '/', specimens: '/specimens', 'specimen-detail': '/specimens/:id',
  equipment: '/equipment', 'equipment-detail': '/equipment/:id', 'report-new': '/reports/new',
  reports: '/reports', experiments: '/experiments', bookings: '/bookings', consumables: '/consumables',
  runs: '/runs', 'run-edit': '/runs/:id', purchases: '/purchases', 'purchase-detail': '/purchases/:id', members: '/members',
  reimbursements: '/reimbursements', projects: '/projects', meetings: '/meetings', 'purchase-reviews': '/purchases/reviews',
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
  return { fetch, router, global: { plugins: [ElementPlus, createPinia(), router] } }
}

it('shows actual totals and links each reminder to its matching filter', async () => {
  const { global } = await setup('/', {
    ...base,
    manager: {
      equipment_to_check: [], low_stock: [], pending_signups: [], to_purchase: [], to_receive: [],
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
  const { global, fetch, router } = await setup(path)
  const wrapper = mount(view, { global })
  await flushPromises()
  const url = new URL(fetch.mock.calls.find(([url]) => url.startsWith(endpoint))![0], 'https://example.test')
  expect(url.searchParams.get(key)).toBe(value)
  fetch.mockClear()
  await router.push(path.split('?')[0]!)
  await flushPromises()
  const clean = fetch.mock.calls.find(([url]) => url.startsWith(endpoint))
  expect(clean).toBeDefined()
  expect(new URL(clean![0], 'https://example.test').searchParams.has(key)).toBe(false)
  wrapper.unmount()
})

it('remembers the schedule column width set from the divider and resets it on double-click', async () => {
  localStorage.removeItem('lab.workbench.side')
  const { global } = await setup('/')
  const wrapper = mount(WorkbenchView, { global })
  await flushPromises()
  const bar = wrapper.get('[role="separator"]')
  expect(bar.attributes('aria-valuenow')).toBe('400')
  await bar.trigger('keydown', { key: 'ArrowLeft' })
  expect(bar.attributes('aria-valuenow')).toBe('424')
  expect(localStorage.getItem('lab.workbench.side')).toBe('424')
  for (let i = 0; i < 20; i++) await bar.trigger('keydown', { key: 'ArrowLeft' })
  expect(bar.attributes('aria-valuenow')).toBe('720')
  await bar.trigger('dblclick')
  expect(localStorage.getItem('lab.workbench.side')).toBe('400')
  wrapper.unmount()
})

it('reminds a student manager of the weekly report and links new kinds to their filtered lists', async () => {
  const purchase = { id: 4, code: 'PR-2026-0004', owner: { id: 2, name: '学生甲' }, purpose: '探头' }
  const { global } = await setup('/', {
    ...base,
    my: { ...base.my, draft_runs: [{ id: 3, code: 'RUN-2026-0003', title: '成像', status: 'draft' }] },
    supervisor: { week_start: '2026-11-16', missing_reports: [{ id: 5, name: '学生乙' }], pending_reviews: [], purchases_to_review: [] },
    overdue_tasks: 2,
    manager: {
      equipment_to_check: [], low_stock: [], overdue_loans: [], overdue_loans_count: 0, calibration_due: [], calibration_due_count: 0,
      pending_signups: [{ id: 6, name: '新同学' }], to_purchase: [purchase], to_receive: [],
    },
  } as unknown as Dashboard)
  const pinia = global.plugins[1] as ReturnType<typeof createPinia>
  useAuthStore(pinia).user = { id: 2, name: '学生甲', role: 'student', is_manager: true, is_approver: false, is_supervisor: true } as Me
  const wrapper = mount(WorkbenchView, { global })
  await flushPromises()
  const hrefs = wrapper.findAll('a').map((a) => a.attributes('href'))
  expect(wrapper.text()).toContain('写本周周报')
  expect(hrefs).toContain('/reports?tab=missing&week=2026-11-16')
  expect(hrefs).toContain('/runs/3')
  expect(hrefs).toContain('/members')
  expect(hrefs).toContain('/purchases/4')
  expect(wrapper.text()).toContain('组里有 2 个任务已逾期')
  wrapper.unmount()
})

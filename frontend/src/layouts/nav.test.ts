import { expect, it, vi } from 'vitest'
import { defineComponent } from 'vue'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'
import type { Me } from '@/api/types'
import { useAuthStore } from '@/stores/auth'
import { routes as systemRoutes } from '@/modules/system'
import { useNav } from './nav'

// These tests exercise the real route metadata and redirects; the page contents have their own tests.
vi.mock('@/modules/system/views/SystemView.vue', () => ({ default: { template: '<div />' } }))

const page = { template: '<div />' }
const routes = [
  { path: '/', name: 'workbench', component: page },
  { path: '/equipment', name: 'equipment', component: page },
  { path: '/equipment/:id', name: 'equipment-detail', component: page, meta: { menu: 'equipment' } },
  { path: '/bookings', name: 'bookings', component: page },
  { path: '/purchases', name: 'purchases', component: page },
  { path: '/funds', name: 'funds', component: page, meta: { manager: true } },
  ...systemRoutes.map((r) => ({ ...r, path: `/${r.path}` })),
]

async function setup(role: 'student' | 'manager' | 'ops', group: Me['group'] = { id: 1, name: '组' }) {
  const pinia = createPinia()
  setActivePinia(pinia)
  const ops = role === 'ops'
  useAuthStore().user = { role: ops ? 'student' : role, is_supervisor: role === 'manager', is_superuser: ops, group } as Me
  const router = createRouter({ history: createMemoryHistory(), routes })
  let nav!: ReturnType<typeof useNav>
  mount(defineComponent({ setup: () => { nav = useNav() }, template: '<div />' }), { global: { plugins: [pinia, router] } })
  await router.push('/')
  return { router, nav }
}

it('lists only modules and pages the role may open, and highlights the list page of a detail page', async () => {
  const student = await setup('student')
  expect(student.nav.modules.value.map((m) => m.label)).toEqual(['工作台', '设备耗材', '采购经费'])
  expect(student.nav.modules.value.find((m) => m.key === 'money')!.pages.map((p) => p.name)).toEqual(['purchases'])

  const manager = await setup('manager')
  expect(manager.nav.modules.value.find((m) => m.key === 'money')!.pages.map((p) => p.name)).toEqual(['purchases', 'funds'])
  await manager.router.push('/equipment/3')
  expect(manager.nav.current.value?.key).toBe('lab')
  expect(manager.nav.page.value).toBe('equipment')
})

it("gives ops 系统管理's pages as the sidebar itself, and a superuser with a group the usual 系统管理 group", async () => {
  const ops = await setup('ops', null)
  expect(ops.router.currentRoute.value.path).toBe('/') // nothing else here; the real guard sends ops to /system
  expect(ops.nav.modules.value.map((m) => [m.label, m.pages.length])).toEqual([
    ['存储与备份', 1], ['账号', 1], ['课题组', 1], ['邮件', 1], ['版本', 1], ['登录记录', 1],
  ])
  expect(new Set(ops.nav.modules.value.map((m) => m.icon)).size).toBe(6) // each its own icon
  await ops.router.push('/system')
  expect(ops.router.currentRoute.value.name).toBe('system-storage')
  expect(ops.nav.current.value?.key).toBe('system-storage')

  const both = await setup('ops')
  const system = both.nav.modules.value.find((m) => m.key === 'system')!
  expect(system.pages.map((p) => p.label)).toEqual(['存储与备份', '账号', '课题组', '邮件', '版本', '登录记录'])
  expect(both.nav.modules.value.some((m) => m.key === 'lab')).toBe(true)
})

it('keeps the pages a user opens as tabs: lists and records, not the workbench or -new forms, at most ten', async () => {
  const { router } = await setup('manager')
  const { trackTab, openedTabs, setTabTitle, closeTab, neighborTab, closeOtherTabs, closeAllTabs } = await import('./nav')
  router.addRoute({ path: '/equipment/new', name: 'equipment-new', component: page, meta: { menu: 'equipment' } })
  const visit = async (path: string) => {
    await router.push(path)
    trackTab(1, router.currentRoute.value)
  }
  await visit('/') // the workbench is home, not a tab: nothing until something is opened
  expect(openedTabs()).toEqual([])
  await visit('/equipment')
  await visit('/equipment/3')
  await visit('/equipment/3?tab=history') // same record: one tab, keeps the latest address
  await visit('/equipment/new')
  await visit('/system/accounts') // 系统管理 has its sidebar, not tabs
  await visit('/purchases') // another module's page joins the same strip
  expect(openedTabs().map((t) => t.full)).toEqual(['/equipment', '/equipment/3?tab=history', '/purchases'])
  setTabTitle('/equipment/3', 'UT-003 测厚仪')
  expect(openedTabs()[1]!.title).toBe('UT-003 测厚仪')
  for (const id of [4, 5, 6, 7, 8, 9, 10, 11]) await visit(`/equipment/${id}`)
  expect(openedTabs()).toHaveLength(10)
  expect(openedTabs()[0]!.path).toBe('/equipment/3') // the oldest went
  expect(neighborTab('/equipment/5')!.path).toBe('/equipment/6') // closing the one on screen shows the tab after it,
  expect(neighborTab('/equipment/11')!.path).toBe('/equipment/10') // or the one before the last
  closeTab('/equipment/5')
  expect(openedTabs()).toHaveLength(9)
  closeOtherTabs('/equipment/7')
  expect(openedTabs().map((t) => t.path)).toEqual(['/equipment/7'])
  closeAllTabs()
  expect(openedTabs()).toEqual([])
  await router.push('/bookings')
  trackTab(2, router.currentRoute.value) // someone else signed in: none of the last person's tabs
  expect(openedTabs().map((t) => t.full)).toEqual(['/bookings'])
})

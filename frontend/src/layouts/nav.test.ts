import { expect, it } from 'vitest'
import { defineComponent } from 'vue'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'
import type { Me } from '@/api/types'
import { useAuthStore } from '@/stores/auth'
import { useNav } from './nav'

const page = { template: '<div />' }
const routes = [
  { path: '/', name: 'workbench', component: page },
  { path: '/equipment', name: 'equipment', component: page },
  { path: '/equipment/:id', name: 'equipment-detail', component: page, meta: { menu: 'equipment' } },
  { path: '/bookings', name: 'bookings', component: page },
  { path: '/purchases', name: 'purchases', component: page },
  { path: '/funds', name: 'funds', component: page, meta: { manager: true } },
]

async function setup(role: 'student' | 'manager') {
  const pinia = createPinia()
  setActivePinia(pinia)
  useAuthStore().user = { role, is_supervisor: role === 'manager', is_superuser: false, group: { id: 1, name: '组' } } as Me
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

it('keeps the pages a user opens as tabs: lists and records, not the workbench or -new forms, at most ten', async () => {
  const { router } = await setup('manager')
  const { trackTab, openedTabs, setTabTitle, closeTab } = await import('./nav')
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
  await visit('/purchases') // another module's page joins the same strip
  expect(openedTabs().map((t) => t.full)).toEqual(['/equipment', '/equipment/3?tab=history', '/purchases'])
  setTabTitle('/equipment/3', 'UT-003 测厚仪')
  expect(openedTabs()[1]!.title).toBe('UT-003 测厚仪')
  for (const id of [4, 5, 6, 7, 8, 9, 10, 11]) await visit(`/equipment/${id}`)
  expect(openedTabs()).toHaveLength(10)
  expect(openedTabs()[0]!.path).toBe('/equipment/3') // the oldest went
  expect(closeTab('/equipment/5')).toBe('/equipment/6') // closing shows the tab after it,
  expect(closeTab('/equipment/11')).toBe('/equipment/10') // or the one before the last
  await router.push('/bookings')
  trackTab(2, router.currentRoute.value) // someone else signed in: none of the last person's tabs
  expect(openedTabs().map((t) => t.full)).toEqual(['/bookings'])
})

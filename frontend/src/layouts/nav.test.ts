import { expect, it } from 'vitest'
import { defineComponent, nextTick } from 'vue'
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

it('sends a module back to the page last opened in it', async () => {
  const { router, nav } = await setup('manager')
  const lab = () => nav.modules.value.find((m) => m.key === 'lab')!
  const money = () => nav.modules.value.find((m) => m.key === 'money')!
  expect(nav.target(money())).toEqual({ name: 'purchases' }) // never opened: its first page
  await router.push('/bookings')
  await router.push('/purchases')
  await nextTick()
  expect(nav.target(lab())).toBe('/bookings')
  await router.push('/equipment/3') // an opened record counts too
  await router.push('/purchases')
  await nextTick()
  expect(nav.target(lab())).toBe('/equipment/3')
})

it('keeps opened records as tabs on every page: once each, not the -new forms, at most eight, closable', async () => {
  const { router } = await setup('manager')
  const { trackTab, openedTabs, setTabTitle, closeTab } = await import('./nav')
  router.addRoute({ path: '/equipment/new', name: 'equipment-new', component: page, meta: { menu: 'equipment' } })
  const visit = async (path: string) => {
    await router.push(path)
    trackTab(1, router.currentRoute.value)
  }
  await visit('/equipment/3')
  await visit('/equipment/3?tab=history') // same record: one tab, keeps the latest address
  await visit('/equipment/new')
  await visit('/purchases') // a list page in another module is not a tab, and the record's tab stays
  expect(openedTabs().map((t) => t.full)).toEqual(['/equipment/3?tab=history'])
  setTabTitle('/equipment/3', 'UT-003 测厚仪')
  expect(openedTabs()[0]!.title).toBe('UT-003 测厚仪')
  for (const id of [4, 5, 6, 7, 8, 9, 10, 11]) await visit(`/equipment/${id}`)
  expect(openedTabs().map((t) => t.path)).toEqual([4, 5, 6, 7, 8, 9, 10, 11].map((id) => `/equipment/${id}`))
  closeTab('/equipment/11')
  expect(openedTabs()).toHaveLength(7)
  await router.push('/bookings')
  trackTab(2, router.currentRoute.value) // someone else signed in: nothing of the last person's
  expect(openedTabs()).toEqual([])
})

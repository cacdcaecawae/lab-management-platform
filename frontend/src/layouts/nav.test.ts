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
  expect(nav.target(lab())).toEqual({ name: 'equipment' })
  await router.push('/bookings')
  await router.push('/purchases')
  await nextTick()
  expect(nav.target(lab())).toEqual({ name: 'bookings' })
})

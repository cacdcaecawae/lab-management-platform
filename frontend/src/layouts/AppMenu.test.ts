import { beforeEach, expect, it } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { createPinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'
import type { Me } from '@/api/types'
import { useAuthStore } from '@/stores/auth'
import AppMenu from './AppMenu.vue'

const page = { template: '<div />' }
const routes = ['workbench', 'equipment', 'bookings', 'purchases', 'reimbursements'].map((name) => ({ path: `/${name}`, name, component: page }))

beforeEach(() => localStorage.clear())

async function setup() {
  const pinia = createPinia()
  useAuthStore(pinia).user = { role: 'student', is_supervisor: false, is_superuser: false, group: { id: 1, name: '组' } } as Me
  const router = createRouter({ history: createMemoryHistory(), routes })
  await router.push('/workbench')
  const wrapper = mount(AppMenu, { global: { plugins: [ElementPlus, pinia, router] } })
  await flushPromises()
  const open = () => wrapper.findAll('.el-sub-menu.is-opened .el-sub-menu__title').map((t) => t.text())
  return { router, wrapper, open }
}

it("opens the group of the page on screen and closes it again when you leave, unless you opened it", async () => {
  const { router, wrapper, open } = await setup()
  expect(open()).toEqual([]) // the workbench is in no group
  await router.push('/equipment')
  await flushPromises()
  expect(open()).toEqual(['设备耗材'])
  await router.push('/purchases')
  await flushPromises()
  expect(open()).toEqual(['采购经费']) // 设备耗材 closed by itself

  const lab = wrapper.findAll('.el-sub-menu__title').find((t) => t.text() === '设备耗材')!
  await lab.trigger('click') // the user opens it: it stays open
  await router.push('/workbench')
  await flushPromises()
  expect(open()).toEqual(['设备耗材'])
  expect(JSON.parse(localStorage.getItem('lab.menu.open')!)).toEqual(['lab'])
  wrapper.unmount()
})

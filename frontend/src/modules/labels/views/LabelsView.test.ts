import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { beforeEach, expect, it, vi } from 'vitest'
import LabelsView from './LabelsView.vue'

const mocks = vi.hoisted(() => ({ equipment: vi.fn(), specimen: vi.fn(), consumables: vi.fn(), encode: vi.fn() }))
vi.mock('@/modules/equipment/api', () => ({ equipmentApi: { get: mocks.equipment } }))
vi.mock('@/modules/specimens/api', () => ({ specimensApi: { get: mocks.specimen } }))
vi.mock('@/modules/inventory/api', () => ({ consumablesApi: { list: mocks.consumables } }))
vi.mock('qrcode', () => ({ default: { toDataURL: mocks.encode } }))

async function show(path: string) {
  const empty = { template: '<span />' }
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/labels', component: LabelsView },
      { path: '/equipment', name: 'equipment', component: empty },
      { path: '/specimens', name: 'specimens', component: empty },
      { path: '/equipment/:id', name: 'equipment-detail', component: empty },
      { path: '/specimens/:id', name: 'specimen-detail', component: empty },
      { path: '/consumables', name: 'consumables', component: empty },
    ],
  })
  await router.push(path)
  const wrapper = mount(LabelsView, { global: {
    plugins: [router],
    stubs: {
      'el-alert': { props: ['title'], template: '<p>{{ title }}</p>' },
      'el-button': { props: ['disabled'], template: '<button :disabled="disabled"><slot /></button>' },
    },
  } })
  await flushPromises()
  return { wrapper, router }
}

beforeEach(() => {
  vi.resetAllMocks()
  mocks.equipment.mockImplementation(async (id) => ({ code: `EQ-${id}`, name: '示波器' }))
  mocks.specimen.mockImplementation(async (id) => ({ code: `SP-${id}`, name: '标准试块', defects: 'DO NOT PRINT' }))
  mocks.encode.mockResolvedValue('data:image/png;base64,AQ==')
})

it('encodes real detail destinations with no label metadata, retaining selection order and removing duplicates', async () => {
  const { wrapper } = await show('/labels?type=equipment&ids=9,2,9,10')
  expect(mocks.equipment.mock.calls.map(([id]) => id)).toEqual([9, 2, 10])
  expect(mocks.specimen).not.toHaveBeenCalled()
  expect(mocks.encode.mock.calls.map(([url]) => url)).toEqual([9, 2, 10].map((id) => `${location.origin}/equipment/${id}`))
  expect(wrapper.findAll('.label').map((x) => x.find('a').text())).toEqual(['EQ-9', 'EQ-2', 'EQ-10'])
  expect(wrapper.text()).toContain(location.origin)
  expect(wrapper.text()).toContain('示波器')
  const print = vi.spyOn(window, 'print').mockImplementation(() => {})
  await wrapper.find('button').trigger('click')
  expect(print).toHaveBeenCalledOnce()
  print.mockRestore()
  wrapper.unmount()
})

it('renders 24 labels per sheet, with specimen names and codes only', async () => {
  const ids = Array.from({ length: 25 }, (_, i) => i + 1)
  const { wrapper } = await show(`/labels?type=specimen&ids=${ids.join(',')}`)
  expect(wrapper.findAll('.label-sheet').map((x) => x.findAll('.label').length)).toEqual([24, 1])
  expect(wrapper.text()).not.toContain('DO NOT PRINT')
  expect(mocks.encode.mock.calls[24]?.[0]).toBe(`${location.origin}/specimens/25`)
  wrapper.unmount()
})

it.each([
  '/labels?type=other&ids=1',
  '/labels?type=equipment&ids=1,0',
  '/labels?type=equipment&ids=9007199254740992',
  '/labels?type=equipment&ids=1&ids=2',
  `/labels?type=equipment&ids=${Array(97).fill('1').join(',')}`,
])('does not fetch or print invalid requests: %s', async (path) => {
  const { wrapper } = await show(path)
  expect(mocks.equipment).not.toHaveBeenCalled()
  expect(mocks.specimen).not.toHaveBeenCalled()
  expect(wrapper.find('button').element.disabled).toBe(true)
  wrapper.unmount()
})

it('does not print a partial batch or expose an inaccessible label', async () => {
  mocks.equipment.mockRejectedValueOnce(new Error('not found'))
  const { wrapper } = await show('/labels?type=equipment&ids=1,2')
  expect(wrapper.findAll('.label')).toHaveLength(0)
  expect(wrapper.findAll('button').at(-1)?.element.disabled).toBe(true)
  expect(wrapper.text()).toContain('1 项未能生成')
  wrapper.unmount()
})

it('ignores outdated responses when navigating within the print page', async () => {
  let resolve!: (value: { code: string; name: string }) => void
  mocks.equipment.mockImplementationOnce(() => new Promise((r) => { resolve = r }))
  const { wrapper, router } = await show('/labels?type=equipment&ids=1')
  await router.push('/labels?type=specimen&ids=2')
  await flushPromises()
  resolve({ code: 'outdated', name: 'outdated' })
  await flushPromises()
  expect(wrapper.find('.label').text()).toContain('SP-2')
  expect(wrapper.text()).not.toContain('outdated')
  expect(mocks.encode).toHaveBeenCalledTimes(1)
  wrapper.unmount()
})

it('points a consumable label at taking it out, and prints its name, spec and place', async () => {
  mocks.consumables.mockImplementation(async ({ item }: { item: number }) => ({
    results: [{ id: item, name: '耦合剂', spec: '250 mL', location: 'A302' }],
  }))
  const { wrapper } = await show('/labels?type=consumable&ids=4')
  expect(mocks.encode.mock.calls[0]?.[0]).toBe(`${location.origin}/consumables?item=4&scan=1`)
  expect(wrapper.find('.label').text()).toContain('耦合剂')
  expect(wrapper.find('.label').text()).toContain('250 mL · A302')
  expect(wrapper.text()).toContain('返回耗材库存')
  wrapper.unmount()
})

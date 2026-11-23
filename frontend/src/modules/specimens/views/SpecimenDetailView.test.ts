import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import type { Specimen, SpecimenLoan } from '@/api/types'
import SpecimenDetailView from './SpecimenDetailView.vue'

const api = vi.hoisted(() => ({ get: vi.fn(), loans: vi.fn(), giveBack: vi.fn() }))
vi.mock('../api', () => ({ specimensApi: api }))
vi.mock('@/modules/projects/api', () => ({ projectsApi: { list: () => Promise.resolve({ results: [] }) } }))
vi.mock('@/stores/auth', () => ({ useAuthStore: () => ({ user: { id: 1 }, isManager: true, isSupervisor: true }) }))
vi.mock('vue-router', () => ({ useRoute: () => ({ params: { id: '3' } }), useRouter: () => ({ push: vi.fn() }) }))

const makeLoan = (id: number): SpecimenLoan => ({
  id,
  borrower: { id: 2, name: 'A' },
  project: null,
  purpose: '',
  due_date: null,
  borrowed_at: '',
  returned_at: null,
  returned_by: null,
  return_note: '',
  return_location: '',
  return_photo_url: null,
})
let block: Specimen

beforeEach(() => {
  vi.clearAllMocks()
  block = {
    id: 3,
    code: 'S',
    name: '试件',
    status: 'available',
    kind: 'standard',
    material: '',
    dimensions: '',
    location: '',
    custodian: null,
    defects_public: false,
    current_loan: makeLoan(11),
    latest_return_photo: null,
    notes: '',
    defects: [],
    created_at: '',
    updated_at: '',
  }
  api.get.mockImplementation(() => Promise.resolve(block))
  api.loans.mockResolvedValue({ results: [] })
  api.giveBack.mockResolvedValue({})
})
afterEach(() => vi.restoreAllMocks())

async function open() {
  const wrapper = mount(SpecimenDetailView, {
    global: {
      plugins: [ElementPlus],
      stubs: { SpecimenFormDialog: true, HistoryDrawer: true, teleport: true },
    },
  })
  await flushPromises()
  await wrapper.findAll('button').find((b) => b.text() === '登记归还')!.trigger('click')
  await flushPromises()
  return wrapper
}

function submitReturnDialog(wrapper: ReturnType<typeof mount>) {
  // Dialog submit button is the last "登记归还" button rendered inside FormDialog
  const buttons = wrapper.findAll('button').filter((b) => b.text() === '登记归还')
  return buttons.at(-1)!.trigger('click')
}

it('captures the displayed loan before confirmation, not the later current loan', async () => {
  const wrapper = await open()
  block.current_loan = makeLoan(12) // state changes while the dialog is open
  const inputs = wrapper.findAll('input[type="text"], input:not([type])')
  await inputs[inputs.length - 2]!.setValue(' A302 试块柜 ')
  await inputs[inputs.length - 1]!.setValue(' 完好 ')
  await submitReturnDialog(wrapper)
  await flushPromises()
  expect(api.giveBack).toHaveBeenCalledWith(3, 11, { note: '完好', return_location: 'A302 试块柜', photo: null })
  expect(api.get).toHaveBeenCalledTimes(2)
  wrapper.unmount()
})

it('does not return anything when the confirmation is canceled', async () => {
  const wrapper = await open()
  const cancelBtn = wrapper.findAll('button').find((b) => b.text() === '取消')!
  await cancelBtn.trigger('click')
  await flushPromises()
  expect(api.giveBack).not.toHaveBeenCalled()
  wrapper.unmount()
})

it('refreshes after stale rejection without retrying the return', async () => {
  const { ApiError } = await import('@/api/client')
  api.giveBack.mockRejectedValue(new ApiError(409, { code: 'stale_loan', message: '借用记录已变化，请刷新后重新核对' }))
  const wrapper = await open()
  await submitReturnDialog(wrapper)
  await flushPromises()
  expect(api.giveBack).toHaveBeenCalledTimes(1)
  expect(api.get).toHaveBeenCalledTimes(2)
  wrapper.unmount()
})

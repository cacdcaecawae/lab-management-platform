import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus, { ElMessageBox } from 'element-plus'
import type { Specimen, SpecimenLoan } from '@/api/types'
import SpecimenDetailView from './SpecimenDetailView.vue'

const api = vi.hoisted(() => ({ get: vi.fn(), loans: vi.fn(), giveBack: vi.fn() }))
vi.mock('../api', () => ({ specimensApi: api }))
vi.mock('@/api/projects', () => ({ projectsApi: { list: () => Promise.resolve({ results: [] }) } }))
vi.mock('@/stores/auth', () => ({ useAuthStore: () => ({ user: { id: 1 }, isManager: true, isSupervisor: true }) }))
vi.mock('vue-router', () => ({ useRoute: () => ({ params: { id: '3' } }), useRouter: () => ({ push: vi.fn() }) }))

// Element Plus declares an intersection with Action; prompt actually resolves this object.
const confirmed = (value: string) => ({ value, action: 'confirm' }) as Awaited<ReturnType<typeof ElMessageBox.prompt>>

const makeLoan = (id: number): SpecimenLoan => ({ id, borrower: { id: 2, name: 'A' }, project: null, purpose: '', due_date: null,
  borrowed_at: '', returned_at: null, returned_by: null, return_note: '' })
let block: Specimen
beforeEach(() => {
  vi.clearAllMocks()
  block = { id: 3, code: 'S', name: '试件', status: 'available', kind: 'standard', material: '', dimensions: '', location: '',
    custodian: null, defects_public: false, current_loan: makeLoan(11), notes: '', defects: [], created_at: '', updated_at: '' }
  api.get.mockImplementation(() => Promise.resolve(block))
  api.loans.mockResolvedValue({ results: [] })
  api.giveBack.mockResolvedValue({})
})
afterEach(() => vi.restoreAllMocks())
async function open() {
  const wrapper = mount(SpecimenDetailView, { global: { plugins: [ElementPlus], stubs: { SpecimenFormDialog: true, HistoryDrawer: true } } })
  await flushPromises()
  await wrapper.findAll('button').find(b => b.text() === '登记归还')!.trigger('click')
  return wrapper
}

it('captures the displayed loan before confirmation, not the later current loan', async () => {
  let confirm!: (value: Awaited<ReturnType<typeof ElMessageBox.prompt>>) => void
  vi.spyOn(ElMessageBox, 'prompt').mockImplementation(() => new Promise(resolve => { confirm = resolve }))
  const wrapper = await open()
  block.current_loan = makeLoan(12) // state changes while the asynchronous dialog is open
  confirm(confirmed(' 完好 '))
  await flushPromises()
  expect(api.giveBack).toHaveBeenCalledWith(3, 11, '完好')
  expect(api.get).toHaveBeenCalledTimes(2)
  wrapper.unmount()
})

it('does not return anything when the confirmation is canceled', async () => {
  vi.spyOn(ElMessageBox, 'prompt').mockRejectedValue('cancel')
  const wrapper = await open()
  await flushPromises()
  expect(api.giveBack).not.toHaveBeenCalled()
  wrapper.unmount()
})

it('refreshes after stale rejection without retrying the return', async () => {
  vi.spyOn(ElMessageBox, 'prompt').mockResolvedValue(confirmed(''))
  const { ApiError } = await import('@/api/client')
  api.giveBack.mockRejectedValue(new ApiError(409, { code: 'stale_loan', message: '借用记录已变化，请刷新后重新核对' }))
  const wrapper = await open()
  await flushPromises()
  expect(api.giveBack).toHaveBeenCalledTimes(1)
  expect(api.get).toHaveBeenCalledTimes(2)
  wrapper.unmount()
})

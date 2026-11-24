import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import type { Specimen, SpecimenLoan } from '@/api/types'
import SpecimenDetailView from './SpecimenDetailView.vue'

const api = vi.hoisted(() => ({ get: vi.fn(), loans: vi.fn(), giveBack: vi.fn() }))
const preparePhotoMock = vi.hoisted(() => vi.fn<(file: File) => Promise<File>>())
vi.mock('../api', () => ({ specimensApi: api }))
vi.mock('@/utils/image', () => ({ preparePhoto: preparePhotoMock }))
vi.mock('@/modules/projects/api', () => ({ projectsApi: { list: () => Promise.resolve({ results: [] }) } }))
vi.mock('@/stores/auth', () => ({ useAuthStore: () => ({ user: { id: 1 }, isManager: true, isSupervisor: true }) }))
vi.mock('vue-router', () => ({ useRoute: () => ({ params: { id: '3' } }), useRouter: () => ({ push: vi.fn() }) }))

const makeLoan = (id: number): SpecimenLoan => ({
  id,
  specimen: { id: 3, code: 'S-3', name: '试块' },
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
  preparePhotoMock.mockImplementation((file) => Promise.resolve(file))
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
      stubs: { SpecimenFormDialog: true, HistoryDrawer: true },
    },
  })
  await flushPromises()
  await wrapper.findAll('button').find((b) => b.text() === '登记归还')!.trigger('click')
  await flushPromises()
  return wrapper
}

function returnConfirmButton(wrapper: ReturnType<typeof mount>) {
  const buttons = wrapper.findAll('button').filter((b) => b.text() === '登记归还')
  return buttons.at(-1)!
}

function submitReturnDialog(wrapper: ReturnType<typeof mount>) {
  return returnConfirmButton(wrapper).trigger('click')
}

function pickFile(inputEl: HTMLInputElement, file: File) {
  Object.defineProperty(inputEl, 'files', { value: [file], configurable: true })
  inputEl.dispatchEvent(new Event('change'))
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

it('blocks return submission until selected photo finishes compressing, then sends compressed photo', async () => {
  let resolvePhoto!: (f: File) => void
  preparePhotoMock.mockImplementation(
    () =>
      new Promise<File>((resolve) => {
        resolvePhoto = resolve
      }),
  )
  const wrapper = await open()
  const raw = new File([new Uint8Array(2048)], 'big.png', { type: 'image/png' })
  const compressed = new File([new Uint8Array(512)], 'big.jpg', { type: 'image/jpeg' })
  const fileInput = wrapper.find('input[type="file"]').element as HTMLInputElement
  pickFile(fileInput, raw)
  await flushPromises()

  // While compressing: confirm button is disabled and clicking/submitting must not fire giveBack
  expect(preparePhotoMock).toHaveBeenCalledTimes(1)
  expect(wrapper.text()).toContain('照片处理中')
  expect(returnConfirmButton(wrapper).attributes()).toHaveProperty('disabled')
  await submitReturnDialog(wrapper)
  await wrapper.find('form').trigger('submit')
  await flushPromises()
  expect(api.giveBack).not.toHaveBeenCalled()

  // Once compression finishes: confirm button re-enables and submits the compressed File
  resolvePhoto(compressed)
  await flushPromises()
  expect(returnConfirmButton(wrapper).attributes('disabled')).toBeUndefined()
  await submitReturnDialog(wrapper)
  await flushPromises()
  expect(api.giveBack).toHaveBeenCalledWith(3, 11, { note: '', return_location: '', photo: compressed })
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

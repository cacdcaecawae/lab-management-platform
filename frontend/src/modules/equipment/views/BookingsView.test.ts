import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import type { Booking } from '@/api/types'
import BookingsView from './BookingsView.vue'

const bookingsMock = vi.hoisted(() => ({ list: vi.fn(), get: vi.fn(), report: vi.fn(), cancel: vi.fn() }))
const equipmentMock = vi.hoisted(() => ({ list: vi.fn() }))
const preparePhotoMock = vi.hoisted(() => vi.fn<(file: File) => Promise<File>>())

vi.mock('../api', () => ({ bookingsApi: bookingsMock, equipmentApi: equipmentMock }))
vi.mock('@/modules/projects/api', () => ({ projectsApi: { list: () => Promise.resolve({ results: [] }) } }))
vi.mock('@/utils/image', () => ({ preparePhoto: preparePhotoMock }))
vi.mock('@/stores/auth', () => ({ useAuthStore: () => ({ user: { id: 2, name: '学生甲' }, isManager: false }) }))
vi.mock('vue-router', () => ({
  useRoute: () => ({ query: { booking: '7' } }),
  useRouter: () => ({ replace: vi.fn() }),
}))

const startedBooking: Booking = {
  id: 7,
  equipment: { id: 1, code: 'EQ-01', name: '示波器', status: 'available' },
  user: { id: 2, name: '学生甲' },
  project: null,
  kind: 'use',
  start_at: '2026-01-01T08:00:00+08:00',
  end_at: '2026-01-01T10:00:00+08:00',
  purpose: '采集波形',
  cancelled_at: null,
  report: null,
  created_at: '2026-01-01T07:00:00+08:00',
}

beforeEach(() => {
  vi.clearAllMocks()
  Object.defineProperty(window, 'matchMedia', {
    writable: true,
    value: vi.fn().mockReturnValue({ matches: false, addEventListener: vi.fn(), removeEventListener: vi.fn() }),
  })
  equipmentMock.list.mockResolvedValue({ results: [] })
  bookingsMock.list.mockResolvedValue([])
  bookingsMock.get.mockResolvedValue(startedBooking)
  bookingsMock.report.mockResolvedValue({
    ...startedBooking,
    report: { condition: 'normal', description: '', photo_url: '/api/bookings/7/photo/', reported_at: '2026-01-01T10:05:00+08:00' },
  })
})
afterEach(() => vi.restoreAllMocks())

function pickFile(inputEl: HTMLInputElement, file: File) {
  Object.defineProperty(inputEl, 'files', { value: [file], configurable: true })
  inputEl.dispatchEvent(new Event('change'))
}

it('blocks usage report submission until selected photo finishes compressing', async () => {
  let resolvePhoto!: (f: File) => void
  preparePhotoMock.mockImplementation(
    () =>
      new Promise<File>((resolve) => {
        resolvePhoto = resolve
      }),
  )

  const wrapper = mount(BookingsView, {
    global: {
      plugins: [ElementPlus],
      stubs: {
        FullCalendar: { template: '<div />', methods: { getApi: () => ({ gotoDate: vi.fn(), refetchEvents: vi.fn() }) } },
        BookingFormDialog: true,
        RouterLink: { template: '<a><slot /></a>' },
      },
    },
  })
  await flushPromises()

  const submitBtn = () => wrapper.findAll('button').find((b) => b.text() === '登记')!
  const raw = new File([new Uint8Array(4096)], 'device.png', { type: 'image/png' })
  const compressed = new File([new Uint8Array(512)], 'device.jpg', { type: 'image/jpeg' })

  const fileInput = wrapper.find('input[type="file"]').element as HTMLInputElement
  pickFile(fileInput, raw)
  await flushPromises()

  expect(submitBtn().attributes('disabled')).toBeDefined()
  await submitBtn().trigger('click')
  await flushPromises()
  expect(bookingsMock.report).not.toHaveBeenCalled()

  resolvePhoto(compressed)
  await flushPromises()

  expect(submitBtn().attributes('disabled')).toBeUndefined()
  await submitBtn().trigger('click')
  await flushPromises()
  expect(bookingsMock.report).toHaveBeenCalledWith(7, expect.objectContaining({ condition: 'normal', photo: compressed }))
  wrapper.unmount()
})

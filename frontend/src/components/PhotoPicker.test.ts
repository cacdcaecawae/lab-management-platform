import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import PhotoPicker from './PhotoPicker.vue'

const preparePhotoMock = vi.hoisted(() => vi.fn<(file: File) => Promise<File>>())
vi.mock('@/utils/image', () => ({ preparePhoto: preparePhotoMock }))

function pickFile(inputEl: HTMLInputElement, file: File) {
  Object.defineProperty(inputEl, 'files', { value: [file], configurable: true })
  inputEl.dispatchEvent(new Event('change'))
}

beforeEach(() => {
  vi.clearAllMocks()
})
afterEach(() => vi.restoreAllMocks())

describe('PhotoPicker', () => {
  it('toggles processing model while compressing and discards stale slower picks', async () => {
    const resolvers: Array<(f: File) => void> = []
    preparePhotoMock.mockImplementation(
      () =>
        new Promise<File>((resolve) => {
          resolvers.push(resolve)
        }),
    )

    const wrapper = mount(PhotoPicker, {
      props: { modelValue: null, processing: false },
      global: { plugins: [ElementPlus] },
    })
    const input = wrapper.find('input[type="file"]').element as HTMLInputElement

    const firstRaw = new File(['a'], 'first.png', { type: 'image/png' })
    const secondRaw = new File(['b'], 'second.png', { type: 'image/png' })
    const firstDone = new File(['a1'], 'first.jpg', { type: 'image/jpeg' })
    const secondDone = new File(['b1'], 'second.jpg', { type: 'image/jpeg' })

    pickFile(input, firstRaw)
    await flushPromises()
    expect(wrapper.emitted('update:processing')?.at(-1)).toEqual([true])

    // Second pick supersedes the first before it finishes
    pickFile(input, secondRaw)
    await flushPromises()

    resolvers[1](secondDone)
    await flushPromises()
    expect(wrapper.emitted('update:modelValue')).toEqual([[secondDone]])
    expect(wrapper.emitted('update:processing')?.at(-1)).toEqual([false])

    // Late resolution of first pick is discarded
    resolvers[0](firstDone)
    await flushPromises()
    expect(wrapper.emitted('update:modelValue')).toEqual([[secondDone]])
    wrapper.unmount()
  })

  it('resets processing and discards pending compression on unmount', async () => {
    let resolvePending!: (f: File) => void
    preparePhotoMock.mockImplementation(
      () =>
        new Promise<File>((resolve) => {
          resolvePending = resolve
        }),
    )

    const onProcessing = vi.fn()
    const onModel = vi.fn()
    const wrapper = mount(PhotoPicker, {
      props: {
        modelValue: null,
        processing: false,
        'onUpdate:processing': onProcessing,
        'onUpdate:modelValue': onModel,
      },
      global: { plugins: [ElementPlus] },
    })
    const input = wrapper.find('input[type="file"]').element as HTMLInputElement
    pickFile(input, new File(['a'], 'big.png', { type: 'image/png' }))
    await flushPromises()
    expect(onProcessing).toHaveBeenLastCalledWith(true)

    wrapper.unmount()
    expect(onProcessing).toHaveBeenLastCalledWith(false)

    resolvePending(new File(['done'], 'big.jpg', { type: 'image/jpeg' }))
    await flushPromises()
    expect(onModel).not.toHaveBeenCalled()
  })
})

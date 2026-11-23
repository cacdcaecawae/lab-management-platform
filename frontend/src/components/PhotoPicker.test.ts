import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import PhotoPicker from './PhotoPicker.vue'

const global = { plugins: [ElementPlus] }

describe('PhotoPicker', () => {
  it('shows trigger when empty and emits selected file or null on remove', async () => {
    const file = new File([new Uint8Array([1, 2, 3])], 'bench.jpg', { type: 'image/jpeg' })
    const wrapper = mount(PhotoPicker, { props: { modelValue: null }, global })
    expect(wrapper.text()).toContain('拍照 / 选图')

    const input = wrapper.find('input[type="file"]')
    Object.defineProperty(input.element, 'files', { value: [file], configurable: true })
    await input.trigger('change')
    expect(wrapper.emitted('update:modelValue')?.[0]?.[0]).toBeInstanceOf(File)

    await wrapper.setProps({ modelValue: file })
    expect(wrapper.text()).toContain('bench.jpg')
    const removeBtn = wrapper.findAll('button').find((b) => b.text() === '移除')!
    await removeBtn.trigger('click')
    expect(wrapper.emitted('update:modelValue')?.at(-1)?.[0]).toBeNull()
  })
})

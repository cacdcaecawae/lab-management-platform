import { describe, expect, it, vi } from 'vitest'
import { reactive } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import ParamsEditor from './ParamsEditor.vue'

const global = { plugins: [ElementPlus] }

describe('ParamsEditor', () => {
  // Like a page: the bound value lives in a reactive form, so the editor gets it back as a proxy.
  function mountEditor(params: Record<string, unknown>) {
    const form = reactive({ params })
    const updates = vi.fn()
    const wrapper = mount(ParamsEditor, {
      props: {
        modelValue: form.params,
        'onUpdate:modelValue': (v: Record<string, unknown>) => {
          updates(v)
          form.params = v
          wrapper.setProps({ modelValue: form.params })
        },
      },
      global,
    })
    return { wrapper, form, updates }
  }

  it('turns typed rows into an object', async () => {
    const { wrapper, form, updates } = mountEditor({})
    await wrapper.find('button').trigger('click') // 添加参数
    const [key, value] = wrapper.findAll('input')
    await key.setValue('频率')
    await value.setValue('5 MHz')
    await flushPromises()
    expect(form.params).toEqual({ 频率: '5 MHz' })
    expect(updates.mock.calls.length).toBeLessThan(10) // no update loop through the reactive parent
    expect(wrapper.findAll('input')).toHaveLength(2) // rows were not rebuilt from our own update
  })

  it('rebuilds rows when the parent loads a new record', async () => {
    const { wrapper } = mountEditor({})
    await wrapper.setProps({ modelValue: { 探头: '5L' } })
    expect((wrapper.find('input').element as HTMLInputElement).value).toBe('探头')
  })

  it('shows existing params and flags duplicate names', async () => {
    const { wrapper } = mountEditor({ 增益: 30 })
    expect((wrapper.find('input').element as HTMLInputElement).value).toBe('增益')
    await wrapper.findAll('button').at(-1)!.trigger('click') // 添加参数
    await wrapper.findAll('input')[2].setValue('增益')
    await flushPromises()
    expect(wrapper.text()).toContain('参数名重复：增益')
    expect((wrapper.vm as unknown as { validate: () => boolean }).validate()).toBe(false)
  })
})

import { describe, expect, it, vi } from 'vitest'
import { reactive } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import StatusTag from './StatusTag.vue'
import ParamsEditor from './ParamsEditor.vue'
import PinnedDatasets from './PinnedDatasets.vue'

const global = { plugins: [ElementPlus] }

describe('StatusTag', () => {
  it.each([
    ['draft', '草稿'],
    ['submitted', '已提交'],
    ['needs_revision', '需补充'],
    ['reviewed', '已阅'],
  ])('shows %s as %s', (status, label) => {
    expect(mount(StatusTag, { props: { status }, global }).text()).toBe(label)
  })
})

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

describe('PinnedDatasets', () => {
  it('shows the short version code, the "added since" mark, and older records without a version', () => {
    const datasets = [
      { id: 1, code: 'DS-2026-0001', name: '原始', kind: 'raw' as const, version: 'a'.repeat(64), changed: true },
      { id: 2, code: 'DS-2026-0002', name: '旧', kind: 'raw' as const, version: null, changed: false },
      null,
    ]
    const stubs = { RouterLink: { template: '<a><slot /></a>' } }
    const text = mount(PinnedDatasets, { props: { datasets }, global: { ...global, stubs } }).text()
    expect(text).toContain('DS-2026-0001 原始')
    expect(text).toContain(`@ ${'a'.repeat(12)}`)
    expect(text).not.toContain('a'.repeat(13))
    expect(text).toContain('提交后有新增')
    expect(text).toContain('无版本（旧记录）')
  })
})

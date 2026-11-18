import { describe, expect, it, vi } from 'vitest'
import { reactive } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import StatusTag from './StatusTag.vue'
import ParamsEditor from './ParamsEditor.vue'
import PinnedDatasets from './PinnedDatasets.vue'
import EquipmentFormDialog from './EquipmentFormDialog.vue'
import type { Equipment } from '@/api/types'
import { ApiError } from '@/api/client'

const api = vi.hoisted(() => ({ update: vi.fn(), create: vi.fn() }))
vi.mock('@/api/equipment', () => ({ equipmentApi: { update: api.update, create: api.create } }))
vi.mock('@/api/members', () => ({ membersApi: { list: () => Promise.resolve({ results: [] }) } }))
vi.mock('@/api/procurement', () => ({ purchasesApi: { list: () => Promise.resolve({ results: [] }) } }))

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

describe('EquipmentFormDialog', () => {
  // The custodian has left the group: not in the active-member options, still shown on the device.
  const device: Equipment = {
    id: 7, code: 'UT-001', name: '超声探伤仪', status: 'available', model: 'CTS-9009', category: '', location: 'A305',
    custodian: { id: 9, name: '已离组' }, in_use: false, purchase_date: null, calibration_due: '2027-03-01', notes: '',
    purchase: null, created_at: '', updated_at: '',
  }

  async function openEdit() {
    api.update.mockReset().mockResolvedValue(device)
    // Mounted closed, then opened: the dialog fills its form when it becomes visible.
    const wrapper = mount(EquipmentFormDialog, { props: { modelValue: false, equipment: device }, global })
    await wrapper.setProps({ modelValue: true })
    await flushPromises()
    const field = (label: string) =>
      wrapper.findAll('.el-form-item').find((f) => f.find('.el-form-item__label').text() === label)!.find('input, textarea')
    const save = () => wrapper.findAll('button').find((b) => b.text() === '保存')!.trigger('click')
    return { wrapper, field, save }
  }

  it('sends only the changed fields: no status, no custodian (F1)', async () => {
    const { field, save } = await openEdit()
    await field('存放位置').setValue('B210')
    await save()
    await flushPromises()
    expect(api.update).toHaveBeenCalledWith(7, { location: 'B210' })
  })

  it('sends status when the manager changed it', async () => {
    const { wrapper, save } = await openEdit()
    await wrapper.findAll('.el-radio').find((r) => r.text() === '维修')!.find('input').setValue(true)
    await save()
    await flushPromises()
    expect(api.update).toHaveBeenCalledWith(7, { status: 'repair', status_seen: 'available' })
  })

  it('closes and asks the page to reload when the status moved since opening (R1)', async () => {
    const { wrapper, save } = await openEdit()
    api.update.mockRejectedValue(
      new ApiError(409, { code: 'stale_status', message: '设备状态已被改为“待检查”（你打开时是“可用”），请重新打开编辑框确认' }),
    )
    await wrapper.findAll('.el-radio').find((r) => r.text() === '维修')!.find('input').setValue(true)
    await save()
    await flushPromises()
    expect(wrapper.emitted('stale')).toHaveLength(1)
    expect(wrapper.emitted('update:modelValue')).toEqual([[false]])
    expect(wrapper.emitted('saved')).toBeUndefined()
  })

  it('closes without a request when nothing changed', async () => {
    const { wrapper, save } = await openEdit()
    await save()
    await flushPromises()
    expect(api.update).not.toHaveBeenCalled()
    expect(wrapper.emitted('update:modelValue')).toEqual([[false]])
  })
})

import { describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import EquipmentFormDialog from './EquipmentFormDialog.vue'
import type { Equipment } from '@/api/types'
import { ApiError } from '@/api/client'

const api = vi.hoisted(() => ({ update: vi.fn(), create: vi.fn() }))
vi.mock('../api', () => ({ equipmentApi: { update: api.update, create: api.create } }))
vi.mock('@/modules/members/api', () => ({ membersApi: { list: () => Promise.resolve({ results: [] }) } }))
vi.mock('@/modules/procurement/api', () => ({ purchasesApi: { list: () => Promise.resolve({ results: [] }) } }))

const global = { plugins: [ElementPlus] }

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

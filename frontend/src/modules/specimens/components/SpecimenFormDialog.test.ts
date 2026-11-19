import { describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import type { Specimen } from '@/api/types'
import SpecimenFormDialog from './SpecimenFormDialog.vue'

const api = vi.hoisted(() => ({ create: vi.fn(), update: vi.fn() }))
vi.mock('../api', () => ({ specimensApi: api }))
vi.mock('@/api/members', () => ({ membersApi: { list: () => Promise.resolve({ results: [] }) } }))

const block: Specimen = {
  id: 3, code: 'CSK-IA-01', name: 'CSK-IA 标准试块', status: 'available', kind: 'standard', material: '20 钢',
  dimensions: '', location: 'A305', custodian: null, defects_public: false, current_loan: null, notes: '',
  defects: [{ id: 1, kind: 'sdh', size_mm: '2.00', depth_mm: '15.00', position: '距左端 50 mm', note: '' }],
  created_at: '', updated_at: '',
}

async function open(specimen: Specimen | null) {
  const wrapper = mount(SpecimenFormDialog, { props: { modelValue: false, specimen }, global: { plugins: [ElementPlus] } })
  await wrapper.setProps({ modelValue: true }) // the dialog fills its form when it becomes visible
  await flushPromises()
  const save = async () => {
    await wrapper.findAll('button').find((b) => b.text() === '保存')!.trigger('click')
    await flushPromises()
  }
  return { wrapper, save }
}

describe('SpecimenFormDialog', () => {
  it('creates with the defect rows', async () => {
    api.create.mockReset().mockResolvedValue(block)
    const { wrapper, save } = await open(null)
    await wrapper.find('input[aria-label="编号"], .el-form-item input').setValue('S-01')
    await wrapper.findAll('button').find((b) => b.text() === '添加缺陷')!.trigger('click')
    await wrapper.find('input[aria-label="第 1 个缺陷的位置"]').setValue('中心')
    await save()
    const body = api.create.mock.calls[0][0]
    expect(body.code).toBe('S-01')
    expect(body.defects).toEqual([{ kind: 'fbh', size_mm: null, depth_mm: null, position: '中心', note: '' }])
    expect(body.defects_public).toBe(false)
  })

  it('edits send only what changed: an untouched defect list is not resent', async () => {
    api.update.mockReset().mockResolvedValue(block)
    const { wrapper, save } = await open(block)
    await wrapper.find('input[aria-label="第 1 个缺陷的位置"]').setValue('距左端 50 mm')  // same value typed again
    const location = wrapper.findAll('.el-form-item').find((f) => f.find('.el-form-item__label').text() === '存放位置')!
    await location.find('input').setValue('B210')
    await save()
    expect(api.update).toHaveBeenCalledWith(3, { location: 'B210' })
  })

  it('a changed defect resends the whole list', async () => {
    api.update.mockReset().mockResolvedValue(block)
    const { wrapper, save } = await open(block)
    await wrapper.find('input[aria-label="第 1 个缺陷的位置"]').setValue('距左端 60 mm')
    await save()
    expect(api.update).toHaveBeenCalledWith(3, {
      defects: [{ id: 1, kind: 'sdh', size_mm: 2, depth_mm: 15, position: '距左端 60 mm', note: '' }],
    })
  })
})

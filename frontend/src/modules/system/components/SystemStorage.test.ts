import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import SystemStorage from './SystemStorage.vue'
import { systemApi } from '@/modules/system/api'

vi.mock('@/modules/system/api', () => ({ systemApi: { storage: vi.fn() } }))
vi.mock('@/utils/errors', () => ({ showError: vi.fn() }))

const stubs = {
  ElDescriptions: { template: '<div><slot /></div>' },
  ElDescriptionsItem: { template: '<div><slot /></div>' },
  ElButton: { template: '<button><slot /></button>' },
}

describe('SystemStorage', () => {
  beforeEach(() => vi.mocked(systemApi.storage).mockReset())

  it('reports local mode without claiming backup health', async () => {
    vi.mocked(systemApi.storage).mockResolvedValue({ primary: 'local', nas_ready: null })
    const wrapper = mount(SystemStorage, { global: { stubs } })
    await flushPromises()
    expect(wrapper.text()).toContain('服务器本地卷')
    expect(wrapper.text()).toContain('未启用')
    expect(wrapper.text()).toContain('不代表备份已成功')
  })

  it('refreshes only identity status and shows loss of access', async () => {
    vi.mocked(systemApi.storage)
      .mockResolvedValueOnce({ primary: 'nas', nas_ready: true })
      .mockResolvedValueOnce({ primary: 'nas', nas_ready: false })
    const wrapper = mount(SystemStorage, { global: { stubs } })
    await flushPromises()
    expect(wrapper.text()).toContain('已识别专用目录')
    await wrapper.get('button').trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('不可用，文件操作已暂停')
    expect(systemApi.storage).toHaveBeenCalledTimes(2)
  })
})

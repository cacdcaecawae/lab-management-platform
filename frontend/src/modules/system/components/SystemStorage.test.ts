import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import SystemStorage from './SystemStorage.vue'
import { systemApi, type StorageInfo } from '@/modules/system/api'

vi.mock('@/modules/system/api', () => ({ systemApi: { storage: vi.fn() } }))
vi.mock('@/utils/errors', () => ({ showError: vi.fn() }))

const stubs = {
  ElDescriptions: { template: '<div><slot name="extra" /><slot /></div>' },
  ElDescriptionsItem: { template: '<div><slot /></div>' },
  ElButton: { template: '<button><slot /></button>' },
  ElTag: { template: '<b><slot /></b>' },
  ElTooltip: { template: '<slot />' },
}

const run = (ok: boolean, detail = '', snapshot = '') => ({ finished_at: '2026-11-20T02:31:00+08:00', ok, snapshot, detail })
const none: StorageInfo = {
  primary: 'local',
  nas_ready: null,
  disk_free: 50 * 1024 ** 3,
  disk_low: false,
  backup: { last_ok: null, last_failure: null, overdue: true, failing: false },
  drill: { last: null, overdue: false },
  attention: true,
}

async function show(info: Partial<StorageInfo>) {
  vi.mocked(systemApi.storage).mockResolvedValue({ ...none, ...info })
  const wrapper = mount(SystemStorage, { global: { stubs } })
  await flushPromises()
  return wrapper
}

describe('SystemStorage', () => {
  beforeEach(() => vi.mocked(systemApi.storage).mockReset())

  it('reports local mode and a fresh install with no backup', async () => {
    const wrapper = await show({})
    const text = wrapper.text()
    expect(text).toContain('服务器本地卷')
    expect(text).toContain('未启用')
    expect(text).not.toContain('不代表备份已成功') // states and values only (DESIGN.md)
    expect(text).toContain('尚无成功备份')
    expect(text).toContain('尚无恢复演练')
    expect(wrapper.findAll('b')).toHaveLength(0) // no 逾期 tag before the first backup
    expect(wrapper.emitted('update:info')?.at(-1)).toEqual([expect.objectContaining({ attention: true })])
  })

  it('shows the last good backup, an older failure and a passed drill', async () => {
    const wrapper = await show({
      backup: { last_ok: run(true, '标签 daily', 'abcdef12'), last_failure: run(false, '导出数据库失败'), overdue: false, failing: false },
      drill: { last: run(true, '附件校验 3 项', 'a'.repeat(64)), overdue: false },
      attention: false,
    })
    const text = wrapper.text()
    expect(text).toContain('快照 abcdef12，标签 daily')
    expect(text).toContain('导出数据库失败')
    expect(text).toContain('快照 aaaaaaaa，附件校验 3 项')
    expect(wrapper.findAll('b').map((b) => b.text())).toEqual(['通过'])
    expect(wrapper.find('.failing').exists()).toBe(false)
  })

  it('flags overdue backups and drills and a current failure', async () => {
    const wrapper = await show({
      backup: { last_ok: run(true, '', 'abcdef12'), last_failure: run(false, '写入备份仓库失败'), overdue: true, failing: true },
      drill: { last: run(false, '退出码 1'), overdue: true },
    })
    expect(wrapper.findAll('b').map((b) => b.text())).toEqual(['逾期', '失败', '逾期'])
    expect(wrapper.get('.failing').text()).toContain('写入备份仓库失败')
  })

  it('shows the free space and when it is too low for uploads', async () => {
    expect((await show({})).text()).toContain('未启用50.0 GB') // the row after the NAS check
    const wrapper = await show({ disk_free: 8 * 1024 ** 3, disk_low: true })
    expect(wrapper.text()).toContain('8.0 GB')
    expect(wrapper.findAll('b').map((b) => b.text())).toEqual(['不足，已暂停上传'])
  })

  it('refreshes and shows loss of NAS access', async () => {
    vi.mocked(systemApi.storage)
      .mockResolvedValueOnce({ ...none, primary: 'nas', nas_ready: true })
      .mockResolvedValueOnce({ ...none, primary: 'nas', nas_ready: false })
    const wrapper = mount(SystemStorage, { global: { stubs } })
    await flushPromises()
    expect(wrapper.text()).toContain('已识别专用目录')
    await wrapper.get('button').trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('不可用，文件操作已暂停')
    expect(systemApi.storage).toHaveBeenCalledTimes(2)
  })
})

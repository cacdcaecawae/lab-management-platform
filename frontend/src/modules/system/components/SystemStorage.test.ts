// @vitest-environment jsdom
import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import SystemStorage from './SystemStorage.vue'
import { systemApi, type StorageInfo } from '@/modules/system/api'
import { storageApi, type OpsStorage } from '@/api/storageUsage'

vi.mock('@/modules/system/api', () => ({ systemApi: { storage: vi.fn() } }))
vi.mock('@/api/storageUsage', () => ({ storageApi: { ops: vi.fn() } }))
vi.mock('@/utils/errors', () => ({ showError: vi.fn() }))

const GB = 1024 ** 3
const run = (ok: boolean, detail = '', snapshot = '') => ({ finished_at: '2026-11-20T02:31:00+08:00', ok, snapshot, detail })
const none: StorageInfo = {
  primary: 'local',
  nas_ready: null,
  disk_free: 50 * GB,
  disk_low: false,
  backup: { last_ok: null, last_failure: null, overdue: true, failing: false },
  drill: { last: null, overdue: false },
  attention: true,
}
const empty: OpsStorage = {
  disk: { kind: 'local', filesystem: { total_bytes: 100 * GB, used_bytes: 50 * GB, free_bytes: 50 * GB } },
  groups: [],
  month_keys: ['2026-10', '2026-11'],
  projection: null,
}

async function show(info: Partial<StorageInfo> = {}, usage: Partial<OpsStorage> = {}) {
  vi.mocked(systemApi.storage).mockResolvedValue({ ...none, ...info })
  vi.mocked(storageApi.ops).mockResolvedValue({ ...empty, ...usage })
  // tags as <b>, so a test can list exactly which ones show
  const wrapper = mount(SystemStorage, { global: { plugins: [ElementPlus], stubs: { ElTag: { template: '<b><slot /></b>' } } } })
  await flushPromises()
  return wrapper
}
const tags = (w: Awaited<ReturnType<typeof show>>) => w.findAll('b').map((b) => b.text())

describe('SystemStorage', () => {
  beforeEach(() => vi.clearAllMocks())

  it('reports local mode and a fresh install with no backup', async () => {
    const wrapper = await show()
    const text = wrapper.text()
    expect(text).toContain('服务器本地卷')
    expect(text).not.toContain('NAS 连接检查') // no NAS, no row about it
    expect(text).toContain('尚无成功备份')
    expect(text).toContain('尚无恢复演练')
    expect(tags(wrapper)).toEqual([]) // no 逾期 tag before the first backup
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
    expect(tags(wrapper)).toEqual(['通过'])
    expect(wrapper.find('.failing').exists()).toBe(false)
  })

  it('flags overdue backups and drills and a current failure', async () => {
    const wrapper = await show({
      backup: { last_ok: run(true, '', 'abcdef12'), last_failure: run(false, '写入备份仓库失败'), overdue: true, failing: true },
      drill: { last: run(false, '退出码 1'), overdue: true },
    })
    expect(tags(wrapper)).toEqual(['逾期', '失败', '逾期'])
    expect(wrapper.get('.failing').text()).toContain('写入备份仓库失败')
  })

  it('shows one disk, and the upload spool only when it is the one that runs out first', async () => {
    let wrapper = await show()
    expect(wrapper.text()).toContain('已用 50.0 GB，共 100.0 GB，剩余 50.0 GB')
    expect(wrapper.text()).not.toContain('上传暂存目录')
    // the spool on a smaller disk (a NAS site's /tmp) holds uploads back first
    wrapper = await show({ disk_free: 8 * GB, disk_low: true })
    expect(wrapper.text()).toContain('上传暂存目录')
    expect(wrapper.text()).toContain('剩余 8.0 GB')
    expect(tags(wrapper)).toEqual(['不足，已暂停上传'])
    wrapper = await show({ disk_free: 6 * GB, disk_low: true }, {
      disk: { kind: 'local', filesystem: { total_bytes: 100 * GB, used_bytes: 94 * GB, free_bytes: 6 * GB } },
    })
    expect(wrapper.text()).not.toContain('上传暂存目录')
    expect(tags(wrapper)).toEqual(['不足，已暂停上传'])
    wrapper = await show({}, { disk: { kind: 'non_local', filesystem: null } })
    expect(wrapper.text()).toContain('文件不在本机磁盘上，没有容量数据')
  })

  it('lists each group by module, and only the months with uploads', async () => {
    const MB = 1024 ** 2
    const usage = (known: number, unknown = 0) => ({ known_bytes: known, unknown_files: unknown })
    let wrapper = await show({}, {
      month_keys: ['2026-09', '2026-10', '2026-11'],
      groups: [
        { id: 1, name: '甲组', ...usage(3 * MB, 2), modules: { raw: usage(3 * MB, 2), knowledge: usage(0) }, months: { '2026-10': 3 * MB } },
        { id: 2, name: '乙组', ...usage(0), modules: { raw: usage(0) }, months: {} },
      ],
    })
    const headers = wrapper.findAll('th').map((th) => th.text())
    expect(headers).toEqual(expect.arrayContaining(['课题组', '原始数据', '设备使用照片', '合计', '2026-10']))
    expect(headers).not.toContain('2026-09')
    expect(wrapper.text()).toContain('甲组')
    expect(wrapper.text()).toContain('另 2 个大小未知')
    expect(wrapper.text()).toContain('暂不估算')
    wrapper = await show()
    expect(wrapper.text()).toContain('近 12 个月没有上传过文件')
    expect(wrapper.text()).not.toContain('暂不估算')
  })

  it('checks again, and shows loss of NAS access', async () => {
    vi.mocked(systemApi.storage)
      .mockResolvedValueOnce({ ...none, primary: 'nas', nas_ready: true })
      .mockResolvedValueOnce({ ...none, primary: 'nas', nas_ready: false })
    vi.mocked(storageApi.ops).mockResolvedValue(empty)
    const wrapper = mount(SystemStorage, { global: { plugins: [ElementPlus] } })
    await flushPromises()
    expect(wrapper.text()).toContain('已识别专用目录')
    await wrapper.get('button[aria-label="重新检查"]').trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('不可用，文件操作已暂停')
    expect(systemApi.storage).toHaveBeenCalledTimes(2)
    expect(storageApi.ops).toHaveBeenCalledTimes(2)
  })
})

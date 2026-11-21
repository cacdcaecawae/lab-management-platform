// @vitest-environment jsdom
import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { expect, it, vi } from 'vitest'
import StorageUsage from './StorageUsage.vue'

const api = vi.hoisted(() => ({ ops: vi.fn(), group: vi.fn() }))
vi.mock('@/api/storageUsage', () => ({ storageApi: api }))

it('shows unavailable capacity for non-local storage without substituting a disk', async () => {
  api.ops.mockResolvedValue({ disk: { kind: 'non_local', filesystem: null }, groups: [], month_keys: [], projection: null })
  const page = mount(StorageUsage, { props: { ops: true }, global: { plugins: [ElementPlus] } })
  await flushPromises()
  expect(page.text()).toContain('文件不在本机磁盘上，没有容量数据')
  expect(page.text()).toContain('暂不估算')
  expect(api.group).not.toHaveBeenCalled()
  page.unmount()
})

it('uses only the group summary and labels the member and project breakdown', async () => {
  api.group.mockResolvedValue({
    by_member: [{ id: 1, label: '合成成员', known_bytes: 12, unknown_files: 0 }],
    by_project: [{ id: 2, label: '合成项目', known_bytes: 12, unknown_files: 0 }],
  })
  const calls = api.ops.mock.calls.length
  const page = mount(StorageUsage, { global: { plugins: [ElementPlus] } })
  await flushPromises()
  expect(api.ops.mock.calls.length).toBe(calls)
  expect(page.text()).toContain('合成成员')
  expect(page.text()).toContain('合成项目')
  expect(page.text()).not.toContain('磁盘') // the disk is ops-only
  page.unmount()
})

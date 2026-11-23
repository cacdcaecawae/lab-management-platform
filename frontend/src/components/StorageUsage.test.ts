// @vitest-environment jsdom
import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { expect, it, vi } from 'vitest'
import StorageUsage from './StorageUsage.vue'

const api = vi.hoisted(() => ({ ops: vi.fn(), group: vi.fn() }))
vi.mock('@/api/storageUsage', () => ({ storageApi: api }))

it('uses only the group summary and labels the member and project breakdown', async () => {
  api.group.mockResolvedValue({
    by_member: [{ id: 1, label: '合成成员', known_bytes: 12, unknown_files: 0 }],
    by_project: [{ id: 2, label: '合成项目', known_bytes: 12, unknown_files: 0 }],
  })
  const page = mount(StorageUsage, { global: { plugins: [ElementPlus] } })
  await flushPromises()
  expect(api.ops).not.toHaveBeenCalled() // every group's usage is ops-only (系统管理 → 存储与备份)
  expect(page.text()).toContain('合成成员')
  expect(page.text()).toContain('合成项目')
  expect(page.text()).not.toContain('磁盘')
  page.unmount()
})

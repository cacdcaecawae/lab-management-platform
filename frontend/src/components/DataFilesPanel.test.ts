import { describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { createMemoryHistory, createRouter } from 'vue-router'
import type { DataFile } from '@/api/types'
import DataFilesPanel, { type DataFilesApi } from './DataFilesPanel.vue'

const file = (id: number, name: string, locked = false): DataFile => ({
  id, dataset_id: 5, name, size: 10, sha256: 'a'.repeat(64), uploaded_by: { id: 1, name: '学生甲' },
  uploaded_at: '2026-11-25T10:00:00+08:00', download_url: `/api/files/${id}/download/`, preview_url: `/api/files/${id}/preview/`,
  locked,
})

function fakeApi(listed: DataFile[], pinned: DataFile[] = listed) {
  return {
    files: vi.fn(async (_id: number, version?: string) => (version ? pinned : listed)),
    upload: vi.fn(async () => []),
    remove: vi.fn(async () => undefined),
    zipUrl: (id: number) => `/api/datasets/${id}/download-zip/`,
  } satisfies DataFilesApi
}

async function render(props: Record<string, unknown>) {
  const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/', component: { template: '<div />' } }] })
  await router.push('/')
  const wrapper = mount(DataFilesPanel, { props: props as never, global: { plugins: [ElementPlus, router] } })
  await flushPromises()
  return wrapper
}

const buttons = (w: Awaited<ReturnType<typeof render>>, text: string) => w.findAll('button').filter((b) => b.text() === text)

describe('DataFilesPanel', () => {
  it('lets the owner delete only what no submitted record pins, and marks files added after the pin', async () => {
    const api = fakeApi([file(1, '01.csv', true), file(2, '02.csv')], [file(1, '01.csv', true)])
    const w = await render({ datasetId: 5, api, editable: true, version: 'f'.repeat(64) })
    expect(api.files).toHaveBeenCalledWith(5, 'f'.repeat(64))
    expect(w.text()).toContain('2 个文件')
    expect(buttons(w, '删除')).toHaveLength(1) // 02.csv only: 01.csv is pinned
    const rows = w.findAll('.el-table__body tr').map((r) => r.text())
    expect(rows.find((r) => r.includes('02.csv'))).toContain('提交后新增')
    expect(rows.find((r) => r.includes('01.csv'))).not.toContain('提交后新增')
    expect(w.find('a[href="/api/datasets/5/download-zip/"]').exists()).toBe(true)
  })

  it('shows a reader the files without upload or delete', async () => {
    const w = await render({ datasetId: 5, api: fakeApi([file(2, '02.csv')]), editable: false })
    expect(buttons(w, '上传文件')).toHaveLength(0)
    expect(buttons(w, '删除')).toHaveLength(0)
    expect(w.text()).toContain('02.csv')
  })

  it('saves a new record first, then uploads into its files', async () => {
    const api = fakeApi([])
    const prepare = vi.fn(async () => 9)
    const w = await render({ datasetId: null, api, editable: true, prepare })
    const input = w.find('input[type="file"]')
    const picked = new File(['t,amp'], 'wave.csv')
    Object.defineProperty(input.element, 'files', { value: [picked] })
    await input.trigger('change')
    await flushPromises()
    expect(prepare).toHaveBeenCalledOnce()
    expect(api.upload).toHaveBeenCalledWith(9, picked, expect.any(Function), undefined)
  })
})

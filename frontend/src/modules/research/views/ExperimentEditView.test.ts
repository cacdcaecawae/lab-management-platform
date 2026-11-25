import { afterEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { createPinia } from 'pinia'
import { createMemoryHistory, createRouter, RouterView } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import type { Experiment, Me } from '@/api/types'
import ExperimentEditView from './ExperimentEditView.vue'

afterEach(() => vi.unstubAllGlobals())

const shared: Experiment = {
  id: 7, code: 'EX-2026-0007', project: { id: 2, name: '导波螺栓松动' }, owner: { id: 3, name: '学生乙' }, title: '预紧力 B 组',
  date: '2026-11-24', equipment_item: null, equipment: '', specimen: '', specimen_items: [], params: {}, steps: '', anomalies: '',
  dataset: { id: 40, code: 'DS-2026-0040', name: '预紧力 B 组', kind: 'raw', version: 'c'.repeat(64), changed: false },
  datasets: [], photos: [], file_count: 1, status: 'submitted', submitted_at: '2026-11-24T18:00:00+08:00',
  created_at: '2026-11-24T09:00:00+08:00', updated_at: '2026-11-24T18:00:00+08:00',
}
const dataFile = {
  id: 90, dataset_id: 40, name: 'w.csv', size: 4, sha256: 'b'.repeat(64), uploaded_by: { id: 3, name: '学生乙' },
  uploaded_at: '2026-11-24T10:00:00+08:00', download_url: '/api/files/90/download/', preview_url: '/api/files/90/preview/', locked: true,
}

async function open(path: string) {
  const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    let body: unknown = { count: 0, next: null, previous: null, results: [] }
    if (url === '/api/experiments/7/') body = shared
    if (url.startsWith('/api/datasets/40/files/')) body = [dataFile]
    if (url === '/api/datasets/40/references/') body = { experiments: [{ id: 7, code: shared.code, title: shared.title, status: 'submitted' }], runs: [], reports: [] }
    if (url === '/api/experiments/' && init?.method === 'POST') body = { ...shared, id: 8, owner: { id: 1, name: '学生甲' }, status: 'draft' }
    return new Response(JSON.stringify(body), { status: init?.method === 'POST' ? 201 : 200 })
  })
  vi.stubGlobal('fetch', fetchMock)
  const pinia = createPinia()
  const stub = { template: '<div />' }
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      ...['experiments', 'run-edit', 'report-edit', 'dataset-detail'].map((name) => ({ path: `/${name}/:id?`, name, component: stub })),
      { path: '/experiments/new', name: 'experiment-new', component: ExperimentEditView },
      { path: '/experiments/:id(\\d+)', name: 'experiment-edit', component: ExperimentEditView },
    ],
  })
  await router.push(path)
  await router.isReady()
  useAuthStore(pinia).user = { id: 1, name: '学生甲', role: 'student' } as Me
  const wrapper = mount(RouterView, { global: { plugins: [ElementPlus, pinia, router] } })
  await flushPromises()
  return { wrapper, fetchMock }
}

const button = (w: { findAll: (s: string) => { text: () => string }[] }, text: string) => w.findAll('button').filter((b) => b.text() === text)

describe('ExperimentEditView', () => {
  it('starts a new record from ?project= / ?equipment= / ?date=', async () => {
    const { wrapper, fetchMock } = await open('/experiments/new?project=2&equipment=3&date=2026-11-20')
    expect(wrapper.text()).toContain('新建实验与原始数据')
    const titleItem = wrapper.findAll('.el-form-item').find((item) => item.find('label').text() === '实验名称')!
    await titleItem.find('input').setValue('预紧力 C 组')
    const [save] = button(wrapper, '保存草稿') as unknown as { trigger: (e: string) => Promise<void> }[]
    await save!.trigger('click')
    await flushPromises()
    const [, init] = fetchMock.mock.calls.find(([url, i]) => url === '/api/experiments/' && i?.method === 'POST')!
    expect(JSON.parse(init!.body as string)).toMatchObject({ project_id: 2, equipment_item_id: 3, date: '2026-11-20', title: '预紧力 C 组' })
  })

  it('shows a teammate\'s shared record read-only, with its files and where they are cited', async () => {
    const { wrapper } = await open('/experiments/7')
    expect(wrapper.text()).toContain('学生乙 于')
    expect(wrapper.text()).toContain('记录已锁定。')
    for (const text of ['保存草稿', '提交', '上传文件', '上传附件', '删除']) expect(button(wrapper, text)).toHaveLength(0)
    expect(wrapper.text()).toContain('w.csv')
    expect(wrapper.text()).toContain('被引用处')
    expect(wrapper.text()).toContain('暂无引用') // the record itself is not listed as citing its own data
  })
})

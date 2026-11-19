import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { reactive } from 'vue'
import { expect, it, vi } from 'vitest'
import type { DocDetail } from '@/api/types'
import KnowledgeView from './KnowledgeView.vue'

const get = vi.hoisted(() => vi.fn())
const list = () => Promise.resolve({ results: [], count: 0, next: null, previous: null })
vi.mock('../api', () => ({ docsApi: { get, list: () => list() } }))
vi.mock('@/modules/equipment/api', () => ({ equipmentApi: { list: () => list() } }))
vi.mock('@/stores/auth', () => ({ useAuthStore: () => ({ user: { id: 1 }, isManager: false }) }))
const route = reactive({ query: {} as { doc?: string } })
vi.mock('vue-router', () => ({ useRoute: () => route }))

function doc(id: number): DocDetail {
  return { id, title: `文档 ${id}`, equipment: null, category: 'manual', tags: [], description: '',
    author: { id: 1, name: '学生甲' }, created_at: '', updated_at: '', versions: [], latest: null }
}

it('opens the newest URL-selected document and closes it when the parameter is removed', async () => {
  const pending: Record<number, (doc: DocDetail) => void> = {}
  get.mockImplementation((id: number) => new Promise(resolve => { pending[id] = resolve }))
  const wrapper = mount(KnowledgeView, { attachTo: document.body, global: { plugins: [ElementPlus], stubs: { HistoryDrawer: true } } })
  try {
    route.query.doc = '1'
    await flushPromises()
    route.query.doc = '2'
    await flushPromises()
    pending[2](doc(2))
    await flushPromises()
    pending[1](doc(1))
    await flushPromises()
    expect(document.body.querySelector('.el-dialog__title')?.textContent).toBe('文档 2')
    route.query.doc = '3'
    await flushPromises()
    delete route.query.doc
    await flushPromises()
    pending[3](doc(3))
    await flushPromises()
    expect(wrapper.findComponent({ name: 'ElDialog' }).props('modelValue')).toBe(false)
    expect(document.body.querySelector('.el-dialog__title')?.textContent).not.toBe('文档 3')
  } finally {
    wrapper.unmount()
  }
})

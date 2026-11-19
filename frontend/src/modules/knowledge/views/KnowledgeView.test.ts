import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus, { ElMessageBox } from 'element-plus'
import { reactive } from 'vue'
import { beforeEach, expect, it, vi } from 'vitest'
import type { DocDetail } from '@/api/types'
import KnowledgeView from './KnowledgeView.vue'

const { get, update, addVersion, remove } = vi.hoisted(() => ({ get: vi.fn(), update: vi.fn(), addVersion: vi.fn(), remove: vi.fn() }))
const list = () => Promise.resolve({ results: [], count: 0, next: null, previous: null })
vi.mock('../api', () => ({ docsApi: { get, update, addVersion, remove, list: () => list() } }))
vi.mock('@/modules/equipment/api', () => ({ equipmentApi: { list: () => list() } }))
vi.mock('@/stores/auth', () => ({ useAuthStore: () => ({ user: { id: 1 }, isManager: true }) }))
const route = reactive({ query: {} as { doc?: string } })
vi.mock('vue-router', () => ({
  useRoute: () => route,
  useRouter: () => ({ replace: async ({ query }: { query: typeof route.query }) => { route.query = query } }),
}))

beforeEach(() => {
  route.query = {}
  vi.resetAllMocks()
})

function mountKnowledge() {
  return mount(KnowledgeView, { attachTo: document.body, global: { plugins: [ElementPlus], stubs: { HistoryDrawer: true } } })
}
function title() {
  return document.body.querySelector('.el-dialog__title')?.textContent
}
function press(text: string) {
  const button = [...document.body.querySelectorAll('.el-dialog button')].find(b => b.textContent?.trim() === text)
  expect(button, text).toBeTruthy()
  ;(button as HTMLButtonElement).click()
}
function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (error: Error) => void
  const promise = new Promise<T>((done, fail) => { resolve = done; reject = fail })
  return { promise, resolve, reject }
}

function doc(id: number): DocDetail {
  return { id, title: `文档 ${id}`, equipment: null, category: 'manual', tags: [], description: '',
    author: { id: 1, name: '学生甲' }, created_at: '', updated_at: '', versions: [], latest: null }
}

it('opens the newest URL-selected document and closes it when the parameter is removed', async () => {
  const pending: Record<number, (doc: DocDetail) => void> = {}
  get.mockImplementation((id: number) => new Promise(resolve => { pending[id] = resolve }))
  const wrapper = mountKnowledge()
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


it('hides the previous doc during and after a failed route-selected lookup', async () => {
  const b = deferred<DocDetail>()
  get.mockImplementation((id: number) => id === 1 ? Promise.resolve(doc(1)) : b.promise)
  route.query.doc = '1'
  const wrapper = mountKnowledge()
  try {
    await flushPromises()
    expect(title()).toBe('文档 1')
    route.query.doc = '2'
    await flushPromises()
    expect(wrapper.findComponent({ name: 'ElDialog' }).props('modelValue')).toBe(false)
    expect(wrapper.text()).toContain('正在加载文档')
    b.reject(new Error('not found'))
    await flushPromises()
    expect(wrapper.findComponent({ name: 'ElDialog' }).props('modelValue')).toBe(false)
    expect(wrapper.text()).not.toContain('正在加载文档')
    expect(title()).not.toBe('文档 1')
  } finally { wrapper.unmount() }
})

it('never applies delayed save or upload results to the newly selected doc', async () => {
  const saving = deferred<DocDetail>()
  const upload = deferred<{ number: number }>()
  get.mockImplementation((id: number) => Promise.resolve(doc(id)))
  update.mockReturnValue(saving.promise)
  addVersion.mockReturnValue(upload.promise)
  route.query.doc = '1'
  const wrapper = mountKnowledge()
  try {
    await flushPromises()
    press('保存')
    const picker = document.body.querySelector<HTMLInputElement>('.el-dialog input[type=file]')!
    Object.defineProperty(picker, 'files', { value: [new File(['fixture'], 'one.txt')] })
    picker.dispatchEvent(new Event('change', { bubbles: true }))
    expect(update.mock.calls[0]?.[0]).toBe(1)
    expect(addVersion.mock.calls[0]?.[0]).toBe(1)
    route.query.doc = '2'
    await flushPromises()
    expect(title()).toBe('文档 2')
    saving.resolve({ ...doc(1), title: '旧响应' })
    upload.resolve({ number: 1 })
    await flushPromises()
    expect(title()).toBe('文档 2')
    expect(get.mock.calls.map(([id]) => id)).toEqual([1, 2])
  } finally { wrapper.unmount() }
})

it('keeps the next dialog open when a prior delete completes and clears the URL on manual close', async () => {
  const deleting = deferred<void>()
  get.mockImplementation((id: number) => Promise.resolve(doc(id)))
  remove.mockReturnValue(deleting.promise)
  const confirm = vi.spyOn(ElMessageBox, 'confirm').mockResolvedValue('confirm' as unknown as Awaited<ReturnType<typeof ElMessageBox.confirm>>)
  route.query.doc = '1'
  const wrapper = mountKnowledge()
  try {
    await flushPromises()
    press('删除文档')
    await flushPromises()
    expect(remove).toHaveBeenCalledWith(1)
    route.query.doc = '2'
    await flushPromises()
    deleting.resolve()
    await flushPromises()
    expect(title()).toBe('文档 2')
    press('取消')
    await flushPromises()
    expect(route.query.doc).toBeUndefined()
    route.query.doc = '2'
    await flushPromises()
    expect(title()).toBe('文档 2')
  } finally { confirm.mockRestore(); wrapper.unmount() }
})

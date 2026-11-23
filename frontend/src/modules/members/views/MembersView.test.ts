// The members page by tag: a 终审人 gives the 管理员 tag; a 管理员 edits plain students (and themselves) only.
import { beforeEach, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { createPinia } from 'pinia'
import { useAuthStore } from '@/stores/auth'
import { membersApi } from '@/modules/members/api'
import type { Me, MemberListItem } from '@/api/types'
import MembersView from './MembersView.vue'

vi.mock('@/modules/members/api', () => ({
  membersApi: { list: vi.fn(), setManager: vi.fn(), update: vi.fn(), pending: vi.fn(), signup: vi.fn(), exportUrl: () => '/api/members/export/' },
}))
vi.mock('element-plus', async (original) => ({
  ...(await original<typeof import('element-plus')>()),
  ElMessageBox: { confirm: vi.fn().mockResolvedValue('confirm') },
}))

const person = (id: number, name: string, extra: Partial<MemberListItem> = {}): MemberListItem => ({
  id, name, role: 'student', is_manager: false, is_approver: false, identity: '', enrollment_year: null,
  member_status: 'active', tags: [], research_direction: '', is_active: true, ...extra,
})
const student = person(2, '学生乙', { identity: 'phd', enrollment_year: 2024, tags: ['安全员'] })
const advisor = person(3, '导师甲', { role: 'advisor', is_approver: true })

async function show(me: Partial<Me>) {
  vi.mocked(membersApi.list).mockResolvedValue({ count: 2, next: null, previous: null, results: [student, advisor] })
  vi.mocked(membersApi.pending).mockResolvedValue([])
  vi.mocked(membersApi.signup).mockResolvedValue({ code: '' })
  const pinia = createPinia()
  useAuthStore(pinia).user = { id: 9, name: '我', role: 'student', is_manager: false, is_approver: false, is_supervisor: false, ...me } as Me
  const wrapper = mount(MembersView, { global: { plugins: [ElementPlus, pinia] }, attachTo: document.body })
  await flushPromises()
  const row = (name: string) => wrapper.findAll('.el-table__body tr').find((r) => r.text().includes(name))!
  return { wrapper, row }
}

beforeEach(() => vi.clearAllMocks())

it('shows the base role, tags, identity, year and 词条', async () => {
  const { wrapper, row } = await show({ role: 'advisor', is_approver: true, is_supervisor: true })
  expect(row('导师甲').text()).toContain('导师 · 终审人')
  expect(row('学生乙').text()).toContain('博士生')
  expect(row('学生乙').text()).toContain('2024级')
  expect(row('学生乙').text()).toContain('安全员')
  wrapper.unmount()
})

it('lets the 终审人 give the 管理员 tag', async () => {
  vi.mocked(membersApi.setManager).mockResolvedValue({} as never)
  const { wrapper, row } = await show({ role: 'advisor', is_approver: true, is_supervisor: true })
  await row('学生乙').findAll('button').find((b) => b.text() === '设为管理员')!.trigger('click')
  await flushPromises()
  expect(membersApi.setManager).toHaveBeenCalledWith(2, true)
  expect(row('学生乙').findAll('button').some((b) => b.text() === '编辑')).toBe(false) // not a manager
  wrapper.unmount()
})

it('lets a 管理员 edit plain students only, and hand out no tag', async () => {
  const { wrapper, row } = await show({ is_manager: true, is_supervisor: true })
  const labels = (name: string) => row(name).findAll('button').map((b) => b.text())
  expect(labels('学生乙')).toEqual(expect.arrayContaining(['编辑', '重置密码', '停用']))
  expect(labels('导师甲')).toEqual([])
  expect(row('导师甲').text()).toContain('由运维管理')
  expect(wrapper.text()).not.toContain('设为管理员')
  wrapper.unmount()
})

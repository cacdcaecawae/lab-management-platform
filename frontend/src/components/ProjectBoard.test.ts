import { mount, flushPromises } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { describe, expect, it, vi } from 'vitest'
import { projectsApi } from '@/api/projects'
import type { Project, ProjectTask } from '@/api/types'
import ProjectBoard from './ProjectBoard.vue'

vi.mock('@/api/projects', () => ({ projectsApi: { tasks: vi.fn(), updateTask: vi.fn(), milestones: vi.fn() } }))

const project: Project = {
  id: 4, name: '测试项目', leader: { id: 1, name: '负责人' }, members: [{ id: 2, name: '同学' }],
  status: 'active', description: '', stage: '', latest_log: null, created_at: '', updated_at: '',
}

const task: ProjectTask = {
  id: 42, title: '检查试验记录', description: '', status: 'todo', assignee: { id: 2, name: '同学', current: true },
  milestone: null, created_by: 1, due_date: null, history: [],
}
const empty = { count: 0, previous: null, next: null, results: [] }
const lane = (tasks: ProjectTask[]) => ({ ...empty, count: tasks.length, results: tasks })

function setup(sessionUserId: number) {
  vi.mocked(projectsApi.tasks).mockImplementation(async (_id, q) => q?.status === 'todo' ? lane([task]) : empty)
  vi.mocked(projectsApi.updateTask).mockResolvedValue({ ...task, status: 'doing' })
  return mount(ProjectBoard, { props: { project, sessionUserId, canManage: false, tab: 'tasks' }, global: { plugins: [ElementPlus] } })
}

describe('ProjectBoard', () => {
  it('loads three status lanes and sends a status-only PATCH for a transition', async () => {
    const wrapper = setup(2)
    await flushPromises()
    expect(wrapper.get('[data-status="todo"]').text()).toContain(task.title)
    expect(wrapper.get('[data-status="doing"]').text()).not.toContain(task.title)
    vi.mocked(projectsApi.tasks).mockImplementation(async (_id, q) =>
      q?.status === 'doing' ? lane([{ ...task, status: 'doing' }]) : empty)
    const move = wrapper.findAll('button').find(button => button.text() === '→ 进行中')
    await move!.trigger('click')
    await flushPromises()
    expect(projectsApi.updateTask).toHaveBeenCalledWith(42, { status: 'doing' })
    expect(wrapper.get('[data-status="doing"]').text()).toContain(task.title)
    expect(wrapper.get('[data-status="todo"]').text()).not.toContain(task.title)
  })

  it('lets a nonmember read without create, edit, delete, or move buttons', async () => {
    const wrapper = setup(9)
    await flushPromises()
    expect(wrapper.text()).toContain(task.title)
    expect(wrapper.findAll('button')).toHaveLength(0)
  })
})

import { mount, flushPromises } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { describe, expect, it, vi } from 'vitest'
import { projectsApi } from '@/api/projects'
import type { Project, ProjectMilestone, ProjectTask } from '@/api/types'
import ProjectBoard from './ProjectBoard.vue'

vi.mock('@/api/projects', () => ({ projectsApi: { tasks: vi.fn(), updateTask: vi.fn(), milestones: vi.fn(), updateMilestone: vi.fn() } }))

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

describe('milestone editor', () => {
  it('sends only the edited title, keeping a concurrent completion intact', async () => {
    const baseline: ProjectMilestone = { id: 8, title: '待定里程碑', due_date: null, done_at: null, task_total: 0, task_done: 0 }
    let server = { ...baseline }
    vi.mocked(projectsApi.milestones).mockImplementation(async () => ({ ...empty, count: 1, results: [{ ...server }] }))
    vi.mocked(projectsApi.updateMilestone).mockImplementation(async (_id, body) => {
      server = { ...server, title: body.title ?? server.title }
      if (body.done === false) server.done_at = null
      return server
    })
    const wrapper = mount(ProjectBoard, {
      props: { project, sessionUserId: 1, canManage: true, tab: 'milestones' },
      global: { plugins: [ElementPlus] },
    })
    await flushPromises()
    await wrapper.findAll('button').find(button => button.text() === '编辑')!.trigger('click')
    await flushPromises()
    server.done_at = '2026-11-18T08:00:00Z'
    await wrapper.get('.el-dialog input[maxlength="200"]').setValue('里程碑新标题')
    await wrapper.get('.el-dialog form').trigger('submit')
    await flushPromises()
    expect(projectsApi.updateMilestone).toHaveBeenCalledWith(8, { title: '里程碑新标题' })
    expect(server.done_at).toBe('2026-11-18T08:00:00Z')
    expect(wrapper.text()).toContain('已完成')
  })
})

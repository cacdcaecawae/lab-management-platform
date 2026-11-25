// The workbench's "组里有 N 个任务已逾期" lists the projects with overdue tasks, or opens the only one's task board.
import { afterEach, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { createPinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'
import ProjectsView from './ProjectsView.vue'

afterEach(() => vi.unstubAllGlobals())

const project = (id: number, overdue: number) => ({
  id, name: `项目${id}`, leader: { id: 1, name: '学生甲' }, members: [], stage: '', status: 'active', description: '',
  latest_log: null, overdue_tasks: overdue, created_at: '', updated_at: '',
})

async function open(path: string, projects: unknown[]) {
  const urls: string[] = []
  vi.stubGlobal('fetch', vi.fn(async (url: string) => {
    urls.push(url)
    const results = url.startsWith('/api/projects/') ? projects : []
    return new Response(JSON.stringify({ count: results.length, next: null, previous: null, results }))
  }))
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/projects', name: 'projects', component: ProjectsView },
      { path: '/projects/:id', name: 'project-detail', component: { template: '<div />' } },
    ],
  })
  await router.push(path)
  await router.isReady()
  const wrapper = mount(ProjectsView, { global: { plugins: [ElementPlus, createPinia(), router] } })
  await flushPromises()
  return { wrapper, router, urls }
}

it('opens the task board of the only project with overdue tasks', async () => {
  const { wrapper, router, urls } = await open('/projects?overdue=1', [project(4, 2)])
  expect(urls.some((u) => u.startsWith('/api/projects/?') && u.includes('overdue=1'))).toBe(true)
  expect(router.currentRoute.value.fullPath).toBe('/projects/4?tab=tasks')
  wrapper.unmount()
})

it('lists them when there are several, and marks their overdue tasks', async () => {
  const { wrapper, router } = await open('/projects?overdue=1', [project(4, 2), project(5, 1)])
  expect(router.currentRoute.value.name).toBe('projects')
  expect(wrapper.text()).toContain('2 个任务逾期')
  wrapper.unmount()
})

it('does not jump when the filter is ticked on the page', async () => {
  const { wrapper, router } = await open('/projects', [project(4, 2)])
  await wrapper.findAll('.el-checkbox').find((c) => c.text() === '有逾期任务')!.trigger('click')
  await flushPromises()
  expect(router.currentRoute.value.name).toBe('projects')
  wrapper.unmount()
})

import type { RouteRecordRaw } from 'vue-router'

export const routes: RouteRecordRaw[] = [
  { path: 'projects', name: 'projects', component: () => import('./views/ProjectsView.vue'), meta: { title: '项目列表' } },
  {
    path: 'projects/:id(\\d+)',
    name: 'project-detail',
    component: () => import('./views/ProjectDetailView.vue'),
    meta: { title: '项目详情', menu: 'projects' },
  },
]

import type { RouteRecordRaw } from 'vue-router'

const ExperimentEdit = () => import('./views/ExperimentEditView.vue')

export const routes: RouteRecordRaw[] = [
  { path: 'experiments', name: 'experiments', component: () => import('./views/ExperimentsView.vue'), meta: { title: '实验与原始数据' } },
  { path: 'experiments/new', name: 'experiment-new', component: ExperimentEdit, meta: { title: '新建实验与原始数据', menu: 'experiments' } },
  { path: 'experiments/:id(\\d+)', name: 'experiment-edit', component: ExperimentEdit, meta: { title: '实验与原始数据', menu: 'experiments' } },
]

const RunEdit = () => import('./views/RunEditView.vue')

export const runRoutes: RouteRecordRaw[] = [
  { path: 'runs', name: 'runs', component: () => import('./views/RunsView.vue'), meta: { title: '数据处理' } },
  { path: 'runs/new', name: 'run-new', component: RunEdit, meta: { title: '新建数据处理', menu: 'runs' } },
  { path: 'runs/:id(\\d+)', name: 'run-edit', component: RunEdit, meta: { title: '数据处理', menu: 'runs' } },
]

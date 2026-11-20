import type { RouteRecordRaw } from 'vue-router'

export const routes: RouteRecordRaw[] = [
  { path: '', name: 'workbench', component: () => import('./views/WorkbenchView.vue'), meta: { title: '工作台' } },
]

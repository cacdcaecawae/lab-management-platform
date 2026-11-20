import type { RouteRecordRaw } from 'vue-router'

export const routes: RouteRecordRaw[] = [
  { path: '/labels', name: 'labels', component: () => import('./views/LabelsView.vue'), meta: { title: '打印标签', manager: true } },
]

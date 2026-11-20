import type { RouteRecordRaw } from 'vue-router'

export const routes: RouteRecordRaw[] = [
  { path: 'system', name: 'system', component: () => import('./views/SystemView.vue'), meta: { title: '系统管理', superuser: true } },
]

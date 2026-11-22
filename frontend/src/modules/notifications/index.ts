import type { RouteRecordRaw } from 'vue-router'

export const routes: RouteRecordRaw[] = [
  { path: 'notifications', name: 'notifications', component: () => import('./views/NotificationsView.vue'), meta: { title: '通知' } },
]

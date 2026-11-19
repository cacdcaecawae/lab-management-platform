import type { RouteRecordRaw } from 'vue-router'

export const routes: RouteRecordRaw[] = [
  { path: 'members', name: 'members', component: () => import('./views/MembersView.vue'), meta: { title: '成员' } },
]

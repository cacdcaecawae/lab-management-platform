import type { RouteRecordRaw } from 'vue-router'

export const routes: RouteRecordRaw[] = [
  { path: 'achievements', name: 'achievements', component: () => import('./views/AchievementsView.vue'), meta: { title: '成果归档' } },
]

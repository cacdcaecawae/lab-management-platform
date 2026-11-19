import type { RouteRecordRaw } from 'vue-router'

export const routes: RouteRecordRaw[] = [
  { path: 'knowledge', name: 'knowledge', component: () => import('./views/KnowledgeView.vue'), meta: { title: '知识库' } },
]

import type { RouteRecordRaw } from 'vue-router'

export const routes: RouteRecordRaw[] = [
  { path: 'consumables', name: 'consumables', component: () => import('./views/ConsumablesView.vue'), meta: { title: '耗材库存' } },
]

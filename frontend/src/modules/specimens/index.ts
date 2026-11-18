import type { RouteRecordRaw } from 'vue-router'

export const routes: RouteRecordRaw[] = [
  { path: 'specimens', name: 'specimens', component: () => import('./views/SpecimensView.vue'), meta: { title: '试样与标准件' } },
  {
    path: 'specimens/:id(\\d+)',
    name: 'specimen-detail',
    component: () => import('./views/SpecimenDetailView.vue'),
    meta: { title: '试件', menu: 'specimens' },
  },
]

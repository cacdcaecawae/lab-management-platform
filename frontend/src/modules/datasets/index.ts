import type { RouteRecordRaw } from 'vue-router'

export const routes: RouteRecordRaw[] = [
  { path: 'datasets', name: 'datasets', component: () => import('./views/DatasetsView.vue'), meta: { title: '原始数据' } },
  {
    path: 'datasets/:id(\\d+)',
    name: 'dataset-detail',
    component: () => import('./views/DatasetDetailView.vue'),
    meta: { title: '数据集', menu: 'datasets' },
  },
]

import type { RouteRecordRaw } from 'vue-router'

export const routes: RouteRecordRaw[] = [
  // 原始数据 is part of 实验与原始数据 now: old links (a project's 资产, bookmarks) land there, filters kept.
  { path: 'datasets', name: 'datasets', redirect: (to) => ({ name: 'experiments', query: to.query }) },
  // A record's files on their own: opened from pinned versions (提交时的数据版本), search results and older links.
  {
    path: 'datasets/:id(\\d+)',
    name: 'dataset-detail',
    component: () => import('./views/DatasetDetailView.vue'),
    meta: { title: '数据集', menu: 'experiments' },
  },
]

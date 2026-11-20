import type { RouteRecordRaw } from 'vue-router'

const ReportEdit = () => import('./views/ReportEditView.vue')

export const routes: RouteRecordRaw[] = [
  { path: 'reports', name: 'reports', component: () => import('./views/ReportsView.vue'), meta: { title: '周报' } },
  { path: 'reports/new', name: 'report-new', component: ReportEdit, meta: { title: '写周报', menu: 'reports' } },
  { path: 'reports/:id(\\d+)', name: 'report-edit', component: ReportEdit, meta: { title: '周报', menu: 'reports' } },
]

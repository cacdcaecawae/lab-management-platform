import type { RouteRecordRaw } from 'vue-router'

const MeetingDetail = () => import('./views/MeetingDetailView.vue')

export const routes: RouteRecordRaw[] = [
  { path: 'meetings', name: 'meetings', component: () => import('./views/MeetingsView.vue'), meta: { title: '组会' } },
  { path: 'meetings/new', name: 'meeting-new', component: MeetingDetail, meta: { title: '新建组会', menu: 'meetings', manager: true } },
  { path: 'meetings/:id(\\d+)', name: 'meeting-detail', component: MeetingDetail, meta: { title: '组会', menu: 'meetings' } },
]

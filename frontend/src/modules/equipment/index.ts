import type { RouteRecordRaw } from 'vue-router'

export const routes: RouteRecordRaw[] = [
  { path: 'equipment/stats', name: 'equipment-stats', component: () => import('./views/EquipmentStatsView.vue'), meta: { title: '设备使用统计', menu: 'equipment', supervisor: true } },
  { path: 'equipment', name: 'equipment', component: () => import('./views/EquipmentView.vue'), meta: { title: '设备台账' } },
  {
    path: 'equipment/:id(\\d+)',
    name: 'equipment-detail',
    component: () => import('./views/EquipmentDetailView.vue'),
    meta: { title: '设备', menu: 'equipment' },
  },
  { path: 'bookings', name: 'bookings', component: () => import('./views/BookingsView.vue'), meta: { title: '设备预约' } },
]

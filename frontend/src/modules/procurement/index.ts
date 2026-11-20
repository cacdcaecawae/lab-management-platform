import type { RouteRecordRaw } from 'vue-router'

const Purchases = () => import('./views/PurchasesView.vue')
const PurchaseDetail = () => import('./views/PurchaseDetailView.vue')

export const routes: RouteRecordRaw[] = [
  { path: 'purchases', name: 'purchases', component: Purchases, meta: { title: '采购申请' } },
  { path: 'purchases/reviews', name: 'purchase-reviews', component: Purchases, meta: { title: '我的审批', supervisor: true } },
  { path: 'purchases/new', name: 'purchase-new', component: PurchaseDetail, meta: { title: '新建采购申请', menu: 'purchases' } },
  { path: 'purchases/:id(\\d+)', name: 'purchase-detail', component: PurchaseDetail, meta: { title: '采购申请', menu: 'purchases' } },
  {
    path: 'reimbursements',
    name: 'reimbursements',
    component: () => import('./views/ReimbursementsView.vue'),
    meta: { title: '报销与统计' },
  },
]

export const fundRoutes: RouteRecordRaw[] = [
  { path: 'funds', name: 'funds', component: () => import('./views/FundsView.vue'), meta: { title: '经费来源', manager: true } },
]

import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { authRequired } from '@/api/client'
import AppLayout from '@/layouts/AppLayout.vue'
// Business modules (src/modules/<module>/); the pages still in src/views/ move in once the pilot is confirmed.
import * as equipment from '@/modules/equipment'
import * as knowledge from '@/modules/knowledge'
import * as specimens from '@/modules/specimens'

const ExperimentEdit = () => import('@/views/ExperimentEditView.vue')
const RunEdit = () => import('@/views/RunEditView.vue')
const ReportEdit = () => import('@/views/ReportEditView.vue')
const PurchaseDetail = () => import('@/views/PurchaseDetailView.vue')
const Purchases = () => import('@/views/PurchasesView.vue')
const MeetingDetail = () => import('@/views/MeetingDetailView.vue')

// meta.title: page title; meta.menu: menu item to highlight on detail pages;
// meta.supervisor: only managers / advisors; meta.manager: only managers; meta.superuser: only the ops account
// (UI only — the API enforces it).
export const appRoutes: RouteRecordRaw[] = [
  { path: '', name: 'workbench', component: () => import('@/views/WorkbenchView.vue'), meta: { title: '工作台' } },
  { path: 'members', name: 'members', component: () => import('@/views/MembersView.vue'), meta: { title: '成员' } },
  { path: 'projects', name: 'projects', component: () => import('@/views/ProjectsView.vue'), meta: { title: '项目列表' } },
  {
    path: 'projects/:id(\\d+)',
    name: 'project-detail',
    component: () => import('@/views/ProjectDetailView.vue'),
    meta: { title: '项目详情', menu: 'projects' },
  },
  { path: 'experiments', name: 'experiments', component: () => import('@/views/ExperimentsView.vue'), meta: { title: '实验记录' } },
  { path: 'experiments/new', name: 'experiment-new', component: ExperimentEdit, meta: { title: '新建实验记录', menu: 'experiments' } },
  { path: 'experiments/:id(\\d+)', name: 'experiment-edit', component: ExperimentEdit, meta: { title: '实验记录', menu: 'experiments' } },
  { path: 'datasets', name: 'datasets', component: () => import('@/views/DatasetsView.vue'), meta: { title: '原始数据' } },
  {
    path: 'datasets/:id(\\d+)',
    name: 'dataset-detail',
    component: () => import('@/views/DatasetDetailView.vue'),
    meta: { title: '数据集', menu: 'datasets' },
  },
  { path: 'runs', name: 'runs', component: () => import('@/views/RunsView.vue'), meta: { title: '数据处理' } },
  { path: 'runs/new', name: 'run-new', component: RunEdit, meta: { title: '新建数据处理记录', menu: 'runs' } },
  { path: 'runs/:id(\\d+)', name: 'run-edit', component: RunEdit, meta: { title: '数据处理记录', menu: 'runs' } },
  { path: 'reports', name: 'reports', component: () => import('@/views/ReportsView.vue'), meta: { title: '周报' } },
  { path: 'reports/new', name: 'report-new', component: ReportEdit, meta: { title: '写周报', menu: 'reports' } },
  { path: 'reports/:id(\\d+)', name: 'report-edit', component: ReportEdit, meta: { title: '周报', menu: 'reports' } },
  ...equipment.routes,
  ...specimens.routes,
  { path: 'consumables', name: 'consumables', component: () => import('@/views/ConsumablesView.vue'), meta: { title: '耗材库存' } },
  { path: 'purchases', name: 'purchases', component: Purchases, meta: { title: '采购申请' } },
  { path: 'purchases/reviews', name: 'purchase-reviews', component: Purchases, meta: { title: '我的审批', supervisor: true } },
  { path: 'purchases/new', name: 'purchase-new', component: PurchaseDetail, meta: { title: '新建采购申请', menu: 'purchases' } },
  { path: 'purchases/:id(\\d+)', name: 'purchase-detail', component: PurchaseDetail, meta: { title: '采购申请', menu: 'purchases' } },
  {
    path: 'reimbursements',
    name: 'reimbursements',
    component: () => import('@/views/ReimbursementsView.vue'),
    meta: { title: '报销与统计' },
  },
  ...knowledge.routes,
  { path: 'achievements', name: 'achievements', component: () => import('@/views/AchievementsView.vue'), meta: { title: '成果归档' } },
  { path: 'meetings', name: 'meetings', component: () => import('@/views/MeetingsView.vue'), meta: { title: '组会' } },
  { path: 'meetings/new', name: 'meeting-new', component: MeetingDetail, meta: { title: '新建组会', menu: 'meetings', manager: true } },
  { path: 'meetings/:id(\\d+)', name: 'meeting-detail', component: MeetingDetail, meta: { title: '组会', menu: 'meetings' } },
  { path: 'funds', name: 'funds', component: () => import('@/views/FundsView.vue'), meta: { title: '经费来源', manager: true } },
  { path: 'system', name: 'system', component: () => import('@/views/SystemView.vue'), meta: { title: '系统管理', superuser: true } },
]

const routes: RouteRecordRaw[] = [
  { path: '/login', name: 'login', component: () => import('@/views/LoginView.vue'), meta: { public: true } },
  { path: '/password', name: 'password', component: () => import('@/views/ChangePasswordView.vue') },
  { path: '/', component: AppLayout, children: appRoutes },
  { path: '/:pathMatch(.*)*', name: 'not-found', component: () => import('@/views/NotFoundView.vue') },
]

export const router = createRouter({ history: createWebHistory(), routes })

authRequired.handler = (code) => {
  const auth = useAuthStore()
  if (code === 'password_change_required') {
    if (auth.user) auth.user.must_change_password = true
    router.push({ name: 'password' })
  } else {
    auth.user = null
    router.push({ name: 'login', query: { next: router.currentRoute.value.fullPath } })
  }
}

router.beforeEach(async (to) => {
  const auth = useAuthStore()
  await auth.load()
  if (to.meta.public) return auth.user && to.name === 'login' ? { name: 'workbench' } : true
  if (!auth.user) return { name: 'login', query: { next: to.fullPath } }
  if (auth.user.must_change_password && to.name !== 'password') return { name: 'password' }
  if (to.meta.supervisor && !auth.isSupervisor) return { name: 'workbench' }
  if (to.meta.manager && !auth.isManager) return { name: 'workbench' }
  if (to.meta.superuser && !auth.isSuperuser) return { name: 'workbench' }
  // the ops account has no group, so every business page would only say "no group"; the password page comes first
  if (auth.isSuperuser && !auth.user.group && !to.meta.superuser && to.name !== 'password') return { name: 'system' }
  return true
})

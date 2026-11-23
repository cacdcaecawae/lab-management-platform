import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { authRequired } from '@/api/client'
import { postAuthTarget } from './post-auth'
import AppLayout from '@/layouts/AppLayout.vue'
// Business modules export lazy routes.
import * as equipment from '@/modules/equipment'
import * as knowledge from '@/modules/knowledge'
import * as specimens from '@/modules/specimens'
import * as notifications from '@/modules/notifications'
import * as workbench from '@/modules/workbench'
import * as members from '@/modules/members'
import * as projects from '@/modules/projects'
import * as research from '@/modules/research'
import * as datasets from '@/modules/datasets'
import * as reports from '@/modules/reports'
import * as inventory from '@/modules/inventory'
import * as procurement from '@/modules/procurement'
import * as meetings from '@/modules/meetings'
import * as achievements from '@/modules/achievements'
import * as labels from '@/modules/labels'
import * as system from '@/modules/system'

// meta.title: page title; meta.menu: menu item to highlight on detail pages;
// meta.supervisor: only managers / advisors; meta.manager: only managers; meta.superuser: only the ops account
// (UI only — the API enforces it).
export const appRoutes: RouteRecordRaw[] = [
  ...workbench.routes,
  ...members.routes,
  ...projects.routes,
  ...research.routes,
  ...datasets.routes,
  ...research.runRoutes,
  ...reports.routes,
  ...equipment.routes,
  ...specimens.routes,
  ...notifications.routes,
  ...inventory.routes,
  ...procurement.routes,
  ...knowledge.routes,
  ...achievements.routes,
  ...meetings.routes,
  ...procurement.fundRoutes,
  ...system.routes,
]

const routes: RouteRecordRaw[] = [
  { path: '/login', name: 'login', component: () => import('@/views/LoginView.vue'), meta: { public: true } },
  { path: '/register', name: 'register', component: () => import('@/views/RegisterView.vue'), meta: { public: true } },
  { path: '/password', name: 'password', component: () => import('@/views/ChangePasswordView.vue') },
  ...labels.routes,
  { path: '/', component: AppLayout, children: appRoutes },
  { path: '/:pathMatch(.*)*', name: 'not-found', component: () => import('@/views/NotFoundView.vue') },
]

export const router = createRouter({ history: createWebHistory(), routes })

authRequired.handler = (code) => {
  const auth = useAuthStore()
  if (code === 'password_change_required') {
    if (auth.user) auth.user.must_change_password = true
    const current = router.currentRoute.value
    if (current.name !== 'password') {
      const next = postAuthTarget(router, current.fullPath)
      router.replace({ name: 'password', query: next ? { next } : {} })
    }
  } else {
    auth.user = null
    const current = router.currentRoute.value
    if (current.name !== 'login') {
      const next = postAuthTarget(router, current.name === 'password' ? current.query.next : current.fullPath)
      router.replace({ name: 'login', query: next ? { next } : {} })
    }
  }
}

router.beforeEach(async (to) => {
  const auth = useAuthStore()
  await auth.load()
  if (to.meta.public) {
    // Signed in, a page to return to opens at once; otherwise the home page, whose button then goes in (the sidebar's
    // Phase leads there).
    return (auth.user && to.name === 'login' && postAuthTarget(router, to.query.next)) || true
  }
  if (!auth.user) {
    const next = postAuthTarget(router, to.name === 'password' ? to.query.next : to.fullPath)
    return { name: 'login', query: next ? { next } : {} }
  }
  if (auth.user.must_change_password && to.name !== 'password') {
    const next = postAuthTarget(router, to.fullPath)
    return { name: 'password', query: next ? { next } : {} }
  }
  if (to.meta.supervisor && !auth.isSupervisor) return { name: 'workbench' }
  if (to.meta.manager && !auth.isManager) return { name: 'workbench' }
  if (to.meta.superuser && !auth.isSuperuser) return { name: 'workbench' }
  // the ops account has no group, so every business page would only say "no group"; the password page comes first
  if (auth.isSuperuser && !auth.user.group && !to.meta.superuser && to.name !== 'password') return { name: 'system' }
  return true
})

import type { RouteRecordRaw } from 'vue-router'

// 系统管理 for the ops account: one page each, listed in the sidebar (layouts/nav.ts), all drawn by SystemView.
const page = (path: string, name: string, title: string): RouteRecordRaw => ({
  path: `system/${path}`,
  name,
  component: () => import('./views/SystemView.vue'),
  meta: { title, superuser: true },
})

export const routes: RouteRecordRaw[] = [
  // Ops lands on 存储与备份: whether the backups run is what needs watching.
  { path: 'system', name: 'system', redirect: { name: 'system-storage' } },
  page('storage', 'system-storage', '存储与备份'),
  page('accounts', 'system-accounts', '账号'),
  page('groups', 'system-groups', '课题组'),
  page('mail', 'system-mail', '邮件'),
  page('version', 'system-version', '版本'),
  page('logins', 'system-logins', '登录记录'),
]

import { computed, reactive, ref, watch, type Component } from 'vue'
import { useRoute, useRouter, type RouteLocationNormalizedLoaded } from 'vue-router'
import {
  Bell, Box, ChatDotRound, Collection, House, Key, Memo, Message, Monitor, Notebook, OfficeBuilding, Promotion, Setting, User,
  Wallet,
} from '@element-plus/icons-vue'
import { useAuthStore } from '@/stores/auth'

// DESIGN.md: the sidebar lists the modules; one with several pages is a group that opens and closes.
// color: the module has its own colour (--lab-mod-<key> in theme.css) on its sidebar icon and on its pages' tabs.
// gap: a little space above it.
type Module = {
  key: string; label: string; icon: Component; color?: boolean; gap?: boolean
  pages: { name: string; label: string; icon?: Component }[]
}
const MODULES: Module[] = [
  { key: 'workbench', label: '工作台', icon: House, pages: [{ name: 'workbench', label: '工作台' }] },
  { key: 'notifications', label: '通知', icon: Bell, pages: [{ name: 'notifications', label: '通知' }] },
  { key: 'projects', label: '项目', icon: Collection, color: true, gap: true, pages: [{ name: 'projects', label: '项目' }] },
  {
    key: 'research', label: '科研记录', icon: Memo, color: true,
    pages: [
      { name: 'experiments', label: '实验记录' },
      { name: 'datasets', label: '原始数据' },
      { name: 'runs', label: '数据处理' },
    ],
  },
  {
    key: 'reporting', label: '周报组会', icon: ChatDotRound, color: true,
    pages: [
      { name: 'reports', label: '周报' },
      { name: 'meetings', label: '组会' },
    ],
  },
  {
    key: 'lab', label: '设备耗材', icon: Monitor, color: true,
    pages: [
      { name: 'equipment', label: '设备台账' },
      { name: 'bookings', label: '设备预约' },
      { name: 'consumables', label: '耗材库存' },
      { name: 'specimens', label: '试样与标准件' },
    ],
  },
  {
    key: 'money', label: '采购经费', icon: Wallet, color: true,
    pages: [
      { name: 'purchases', label: '采购申请' },
      { name: 'purchase-reviews', label: '我的审批' },
      { name: 'reimbursements', label: '报销与统计' },
      { name: 'funds', label: '经费来源' },
    ],
  },
  {
    key: 'library', label: '知识成果', icon: Notebook, color: true,
    pages: [
      { name: 'knowledge', label: '知识库' },
      { name: 'achievements', label: '成果归档' },
    ],
  },
  { key: 'members', label: '成员', icon: User, gap: true, pages: [{ name: 'members', label: '成员' }] },
  {
    key: 'system', label: '系统管理', icon: Setting, gap: true,
    // icon: the page's own, for the ops account whose sidebar is only these pages (useNav)
    pages: [
      { name: 'system-storage', label: '存储与备份', icon: Box },
      { name: 'system-accounts', label: '账号', icon: User },
      { name: 'system-groups', label: '课题组', icon: OfficeBuilding },
      { name: 'system-mail', label: '邮件', icon: Message },
      { name: 'system-version', label: '版本', icon: Promotion },
      { name: 'system-logins', label: '登录记录', icon: Key },
    ],
  },
]

// The colour of the module a page belongs to (for its tab); grey for the ones without (通知, 成员).
export function pageColor(page: string) {
  const m = MODULES.find((x) => x.pages.some((p) => p.name === page))
  return m?.color ? `var(--lab-mod-${m.key})` : 'var(--lab-text-3)'
}

// Pages the user has opened (lists and records; not the workbench, the ops pages or the -new forms) are closable tabs
// in the top bar, one strip shared by all modules (DESIGN.md). None at first. Kept for this browser tab only
// (sessionStorage), and only for the user who opened them; the oldest goes past MAX_OPEN.
export interface OpenedTab { path: string; full: string; title: string }
const TABS_KEY = 'lab.tabs'
const MAX_OPEN = 10
const notTab = (name: string) => name === 'workbench' || name.startsWith('system') || name.endsWith('-new')
const restored = (() => {
  try {
    const v = JSON.parse(sessionStorage.getItem(TABS_KEY) ?? '') as { uid: number | null; tabs: OpenedTab[] }
    return Array.isArray(v.tabs) ? v : null
  } catch {
    return null
  }
})()
const opened = reactive(restored ?? { uid: null as number | null, tabs: [] as OpenedTab[] })
watch(opened, (v) => sessionStorage.setItem(TABS_KEY, JSON.stringify(v)), { deep: true })

export const openedTabs = () => opened.tabs

export function trackTab(uid: number | undefined, r: RouteLocationNormalizedLoaded) {
  if (uid == null) return
  if (opened.uid !== uid) Object.assign(opened, { uid, tabs: [] })
  const name = String(r.name ?? '')
  if (!name || notTab(name)) return
  const tab = opened.tabs.find((t) => t.path === r.path)
  if (tab) tab.full = r.fullPath
  else {
    opened.tabs.push({ path: r.path, full: r.fullPath, title: String(r.meta.title ?? '') })
    if (opened.tabs.length > MAX_OPEN) opened.tabs.shift()
  }
}

// PageHeader reports the record's title (e.g. "UT-001 超声探伤仪") once it has loaded.
export function setTabTitle(path: string, title: string) {
  for (const t of opened.tabs) if (t.path === path && title) t.title = title
}

// Where to go when the tab on screen is closed: the tab after it, else the one before.
export function neighborTab(path: string): OpenedTab | undefined {
  const i = opened.tabs.findIndex((t) => t.path === path)
  return opened.tabs[i + 1] ?? opened.tabs[i - 1]
}

export function closeTab(path: string) {
  opened.tabs = opened.tabs.filter((t) => t.path !== path)
}

export function closeOtherTabs(path: string) {
  opened.tabs = opened.tabs.filter((t) => t.path === path)
}

export function closeAllTabs() {
  opened.tabs = []
}

export function clearTabs() {
  Object.assign(opened, { uid: null, tabs: [] })
}

// Sidebar groups the user opened stay open (kept per browser); the group of the page on screen opens by itself and
// closes again when you leave it, so the sidebar does not grow as you browse.
const GROUPS_KEY = 'lab.menu.open'
export const pinnedGroups = new Set<string>(
  (() => {
    try {
      const v: unknown = JSON.parse(localStorage.getItem(GROUPS_KEY) ?? '[]')
      return Array.isArray(v) ? v.map(String) : []
    } catch {
      return []
    }
  })(),
)
export function pinGroup(key: string, open: boolean) {
  if (open) pinnedGroups.add(key)
  else pinnedGroups.delete(key)
  localStorage.setItem(GROUPS_KEY, JSON.stringify([...pinnedGroups]))
}

// The computer's sidebar folded down to its icons (DESIGN.md), kept per browser.
const FOLDED_KEY = 'lab.sidebar.folded'
export const sidebarFolded = ref(localStorage.getItem(FOLDED_KEY) === '1')
watch(sidebarFolded, (v) => localStorage.setItem(FOLDED_KEY, v ? '1' : '0'))

export function useNav() {
  const auth = useAuthStore()
  const route = useRoute()
  const router = useRouter()

  // Only routes that exist and that the role may open (meta.supervisor / meta.manager / meta.superuser).
  // An ops account without a group only gets 系统管理.
  const allowed = (name: string) => {
    const r = router.getRoutes().find((x) => x.name === name)
    if (!r) return false
    if (r.meta.superuser) return auth.isSuperuser
    return !!auth.user?.group && (!r.meta.supervisor || auth.isSupervisor) && (!r.meta.manager || auth.isManager)
  }
  // computed: the role is known only after login, and the layout outlives a logout / login as someone else
  const modules = computed(() => {
    const shown = MODULES.map((m) => ({ ...m, pages: m.pages.filter((p) => allowed(p.name)) })).filter((m) => m.pages.length)
    // Ops without a group sees only 系统管理: its pages are the whole sidebar, so each stands on its own, with its icon.
    const only = shown.length === 1 ? shown[0]! : undefined
    if (!only || only.pages.length < 2) return shown
    return only.pages.map((p) => ({ ...only, key: p.name, label: p.label, icon: p.icon ?? only.icon, gap: false, pages: [p] }))
  })
  // Detail pages highlight their list page (meta.menu).
  const page = computed(() => String(route.meta.menu ?? route.name))
  const current = computed(() => modules.value.find((m) => m.pages.some((p) => p.name === page.value)))

  return { modules, page, current }
}

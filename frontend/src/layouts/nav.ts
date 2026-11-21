import { computed, reactive, watch } from 'vue'
import { useRoute, useRouter, type RouteLocationNormalizedLoaded, type RouteLocationRaw } from 'vue-router'
import { Bell, Collection, House, Memo, Monitor, Notebook, Setting, User, Wallet } from '@element-plus/icons-vue'
import { useAuthStore } from '@/stores/auth'

// DESIGN.md: the sidebar lists modules; a module's pages are tabs in the top bar. gap: a little space above it in the sidebar.
const MODULES = [
  { key: 'workbench', label: '工作台', icon: House, pages: [{ name: 'workbench', label: '工作台' }] },
  { key: 'notifications', label: '通知', icon: Bell, pages: [{ name: 'notifications', label: '通知' }] },
  {
    key: 'research', label: '科研记录', icon: Memo, gap: true,
    pages: [
      { name: 'experiments', label: '实验记录' },
      { name: 'datasets', label: '原始数据' },
      { name: 'runs', label: '数据处理' },
      { name: 'reports', label: '周报' },
    ],
  },
  {
    key: 'lab', label: '设备耗材', icon: Monitor,
    pages: [
      { name: 'equipment', label: '设备台账' },
      { name: 'bookings', label: '设备预约' },
      { name: 'consumables', label: '耗材库存' },
      { name: 'specimens', label: '试样与标准件' },
    ],
  },
  {
    key: 'money', label: '采购经费', icon: Wallet,
    pages: [
      { name: 'purchases', label: '采购申请' },
      { name: 'purchase-reviews', label: '我的审批' },
      { name: 'reimbursements', label: '报销与统计' },
      { name: 'funds', label: '经费来源' },
    ],
  },
  {
    key: 'projects', label: '项目', icon: Collection,
    pages: [
      { name: 'projects', label: '项目列表' },
      { name: 'meetings', label: '组会' },
    ],
  },
  {
    key: 'knowledge', label: '知识成果', icon: Notebook,
    pages: [
      { name: 'knowledge', label: '知识库' },
      { name: 'achievements', label: '成果归档' },
    ],
  },
  { key: 'members', label: '成员', icon: User, gap: true, pages: [{ name: 'members', label: '成员' }] },
  { key: 'system', label: '系统管理', icon: Setting, pages: [{ name: 'system', label: '系统管理' }] },
]

// The page last opened in each module (a list or one of its opened records): clicking the module goes back there.
const last = reactive<Record<string, { page: string; full: string }>>({})

// Records the user has opened (detail pages: routes with meta.menu, except the -new forms), shown as closable tabs
// in the top bar on every page, like a webmail client's open messages (DESIGN.md). Kept for this browser tab only
// (sessionStorage), and only for the user who opened them; the oldest goes past MAX_OPEN.
export interface OpenedTab { path: string; full: string; title: string }
const TABS_KEY = 'lab.tabs'
const MAX_OPEN = 8
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
  if (!r.meta.menu || String(r.name).endsWith('-new')) return
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

export function closeTab(path: string) {
  opened.tabs = opened.tabs.filter((t) => t.path !== path)
  for (const key of Object.keys(last)) if (last[key]!.full.split('?')[0] === path) delete last[key]
}

export function clearTabs() {
  Object.assign(opened, { uid: null, tabs: [] })
}

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
  const modules = computed(() =>
    MODULES.map((m) => ({ ...m, pages: m.pages.filter((p) => allowed(p.name)) })).filter((m) => m.pages.length),
  )
  // Detail pages highlight their list page (meta.menu).
  const page = computed(() => String(route.meta.menu ?? route.name))
  const current = computed(() => modules.value.find((m) => m.pages.some((p) => p.name === page.value)))
  watch(
    () => route.fullPath,
    (full) => current.value && (last[current.value.key] = { page: page.value, full }),
    { immediate: true },
  )
  const target = (m: (typeof modules.value)[number]): RouteLocationRaw => {
    const l = last[m.key]
    return l && m.pages.some((p) => p.name === l.page) ? l.full : { name: m.pages[0]!.name }
  }

  return { modules, page, current, target }
}

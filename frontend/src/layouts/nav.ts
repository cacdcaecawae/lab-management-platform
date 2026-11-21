import { computed, reactive, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
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

// The page last opened in each module: clicking the module goes back there.
const last = reactive<Record<string, string>>({})

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
  watch(page, (p) => current.value && (last[current.value.key] = p), { immediate: true })
  const target = (m: (typeof modules.value)[number]) => ({
    name: m.pages.some((p) => p.name === last[m.key]) ? last[m.key] : m.pages[0]!.name,
  })

  return { modules, page, current, target }
}

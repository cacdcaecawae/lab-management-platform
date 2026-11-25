<script setup lang="ts">
import { computed, ref } from 'vue'
import type { RouteLocationRaw } from 'vue-router'
import { ArrowRight, Plus } from '@element-plus/icons-vue'
import { dashboardApi } from '@/modules/workbench/api'
import type { Dashboard } from '@/api/types'
import { useAuthStore } from '@/stores/auth'
import { formatMoney, formatPeriod, toDateStr } from '@/utils/format'
import { showError } from '@/utils/errors'
import StatusTag from '@/components/StatusTag.vue'

const auth = useAuthStore()
const data = ref<Dashboard | null>(null)
const loading = ref(true)
const todayStr = toDateStr(new Date())
const today = new Date().toLocaleDateString('zh-CN', { month: 'long', day: 'numeric', weekday: 'long' })

dashboardApi
  .get()
  .then((d) => (data.value = d), showError)
  .finally(() => (loading.value = false))

// One line: a link on the left; on the right a hint, a status tag or a red tag. lead: a time in front (the schedule).
interface Row { key: string | number; to: RouteLocationRaw; code?: string; text: string; lead?: string; hint?: string; late?: boolean; status?: string; danger?: string }
// One kind of thing to do. to: the matching filtered list; count: the real total (the API sends at most 20 rows).
interface Kind {
  type: string
  count: number
  to: RouteLocationRaw
  alert?: boolean
  rows?: Row[]
  names?: string[] // e.g. who has not handed in this week's report, on one line
  hint?: string
  action?: { label: string; to: RouteLocationRaw } // nothing to list, one thing to do
}
const me = String(auth.user?.id ?? '')
const total = (k: Kind) => (k.rows && k.rows.length >= 20 && k.count <= 20 ? '20+' : String(k.count))

// The workbench answers "what needs me now" (DESIGN.md).
const kinds = computed<Kind[]>(() => {
  const d = data.value
  if (!d) return []
  const s: Kind[] = []
  if (d.supervisor) {
    const sv = d.supervisor
    s.push(
      {
        type: '待审批采购', count: sv.purchases_to_review.length, to: { name: 'purchase-reviews' }, alert: true,
        rows: sv.purchases_to_review.map((p) => ({
          key: p.id, to: { name: 'purchase-detail', params: { id: p.id }, query: { from: 'reviews' } },
          code: p.code, text: `${p.owner.name} · ${p.purpose}`, hint: `¥ ${formatMoney(p.total)}`,
        })),
      },
      {
        type: '待反馈周报', count: sv.pending_reviews.length, to: { name: 'reports', query: { tab: 'pending' } }, alert: true,
        rows: sv.pending_reviews.map((r) => ({
          key: r.id, to: { name: 'report-edit', params: { id: r.id } }, text: `${r.owner.name} · ${r.week_start} 这一周`,
        })),
      },
      {
        type: '未交周报', count: sv.missing_reports.length, to: { name: 'reports', query: { tab: 'missing', week: sv.week_start } },
        names: sv.missing_reports.map((u) => u.name), hint: `${sv.week_start} 这一周`,
      },
    )
  }
  const my = d.my
  s.push({
    type: '采购被退回', count: my.returned_purchases.length, to: { name: 'purchases', query: { mine: '1', returned: '1' } }, alert: true,
    rows: my.returned_purchases.map((p) => ({ key: p.id, to: { name: 'purchase-detail', params: { id: p.id } }, code: p.code, text: p.purpose, hint: '去修改' })),
  })
  // students write weekly reports, also those with the 管理员 tag (who get the supervisor block for purchases)
  if (auth.user?.role === 'student' && !my.current_week_report) {
    s.push({ type: '本周周报', count: 1, to: { name: 'reports' }, alert: true, action: { label: '写本周周报', to: { name: 'report-new' } } })
  }
  s.push(
    {
      type: '周报需补充', count: my.reports_needing_revision.length, to: { name: 'reports', query: { status: 'needs_revision' } }, alert: true,
      rows: my.reports_needing_revision.map((r) => ({ key: r.id, to: { name: 'report-edit', params: { id: r.id } }, text: `${r.week_start} 这一周` })),
    },
    {
      type: '待登记使用', count: my.unreported_bookings.length, to: { name: 'bookings', query: { view: 'list', pending: '1' } },
      rows: my.unreported_bookings.map((b) => ({
        key: b.id, to: { name: 'bookings', query: { booking: b.id } }, code: b.equipment.code, text: formatPeriod(b.start_at, b.end_at), hint: '去登记',
      })),
    },
    {
      type: '实验未提交', count: my.draft_experiments.length, to: { name: 'experiments', query: { status: 'draft', owner: me } },
      rows: my.draft_experiments.map((x) => ({ key: x.id, to: { name: 'experiment-edit', params: { id: x.id } }, code: x.code, text: x.title, status: x.status })),
    },
    {
      type: '处理记录未提交', count: my.draft_runs?.length ?? 0, to: { name: 'runs', query: { status: 'draft', owner: me } },
      rows: (my.draft_runs ?? []).map((x) => ({ key: x.id, to: { name: 'run-edit', params: { id: x.id } }, code: x.code, text: x.title, status: 'draft' })),
    },
    {
      type: '采购草稿', count: my.draft_purchases?.length ?? 0, to: { name: 'purchases', query: { status: 'draft', mine: '1', returned: '0' } },
      rows: (my.draft_purchases ?? []).map((p) => ({ key: p.id, to: { name: 'purchase-detail', params: { id: p.id } }, code: p.code, text: p.purpose, hint: '去提交' })),
    },
    {
      type: '报销缺发票', count: my.reimbursements_without_invoice?.length ?? 0, to: { name: 'reimbursements', query: { status: 'pending', no_invoice: '1', owner: me } },
      rows: (my.reimbursements_without_invoice ?? []).map((r) => ({
        key: r.id, to: { name: 'reimbursements', query: { item: r.id } }, code: r.code, text: r.description || `¥ ${formatMoney(r.amount)}`, hint: '上传发票',
      })),
    },
    {
      type: '行动项', count: my.action_items.length, to: { name: 'meetings', query: { tab: 'actions', owner: me } }, alert: my.action_items.some((a) => a.due_date && a.due_date < todayStr),
      rows: my.action_items.map((a) => {
        const late = !!a.due_date && a.due_date < todayStr
        return {
          key: a.id, to: { name: 'meeting-detail', params: { id: a.meeting.id } }, text: a.content,
          hint: a.due_date ? `${a.due_date} 截止${late ? '，已逾期' : ''}` : `${a.meeting.date} 组会`, late,
        }
      }),
    },
    {
      type: '任务', count: my.tasks?.length ?? 0, to: { name: 'projects' },
      rows: (my.tasks ?? []).map((t) => ({
        key: t.id, to: { name: 'project-detail', params: { id: t.project.id }, query: { tab: 'tasks' } }, text: t.title,
        hint: t.due_date ? `${t.project.name} · ${t.due_date}` : t.project.name,
      })),
    },
  )
  if (d.manager) {
    const m = d.manager
    s.push(
      {
        type: '待审核注册', count: m.pending_signups?.length ?? 0, to: { name: 'members' }, alert: true,
        names: (m.pending_signups ?? []).map((u) => u.name), hint: '在成员页审核',
      },
      {
        type: '待采购', count: m.to_purchase?.length ?? 0, to: { name: 'purchases', query: { status: 'approved' } },
        rows: (m.to_purchase ?? []).map((p) => ({ key: p.id, to: { name: 'purchase-detail', params: { id: p.id } }, code: p.code, text: `${p.owner.name} · ${p.purpose}`, hint: '已批准' })),
      },
      {
        type: '待到货', count: m.to_receive?.length ?? 0, to: { name: 'purchases', query: { status: 'purchased' } },
        rows: (m.to_receive ?? []).map((p) => ({ key: p.id, to: { name: 'purchase-detail', params: { id: p.id } }, code: p.code, text: `${p.owner.name} · ${p.purpose}`, hint: '已采购' })),
      },
      {
        type: '逾期未还', count: m.overdue_loans_count, to: { name: 'specimens', query: { overdue: '1' } }, alert: true,
        rows: m.overdue_loans.map((l) => ({
          key: l.loan_id, to: { name: 'specimen-detail', params: { id: l.specimen.id } }, code: l.specimen.code, text: l.specimen.name,
          hint: `${l.borrower.name} · 到期 ${l.due_date}`,
        })),
      },
      {
        type: '设备待检查', count: m.equipment_to_check.length, to: { name: 'equipment', query: { status: 'needs_check' } }, alert: true,
        rows: m.equipment_to_check.map((e) => ({ key: e.id, to: { name: 'equipment-detail', params: { id: e.id } }, code: e.code, text: e.name })),
      },
      {
        type: '校准到期', count: m.calibration_due_count, to: { name: 'equipment', query: { calibration_within: '30' } },
        rows: m.calibration_due.map((e) => ({
          key: e.id, to: { name: 'equipment-detail', params: { id: e.id } }, code: e.code, text: e.name,
          hint: `${e.calibration_due} ${e.calibration_due < todayStr ? '已过期' : '到期'}`,
          late: e.calibration_due < todayStr,
        })),
      },
      {
        type: '库存不足', count: m.low_stock.length, to: { name: 'consumables', query: { low: '1' } },
        rows: m.low_stock.map((c) => ({ key: c.id, to: { name: 'consumables', query: { low: '1' } }, text: `${c.name} ${c.spec}`, hint: `剩 ${c.stock} ${c.unit} / 安全库存 ${c.safety_stock}` })),
      },
      {
        type: '批次到期', count: m.expiring_batches?.length ?? 0, to: { name: 'consumables', query: { expiring_within: '30' } },
        rows: (m.expiring_batches ?? []).map((b) => ({
          key: b.id, to: { name: 'consumables', query: { expiring_within: '30' } }, text: `${b.consumable__name} · ${b.batch_no}`,
          hint: `${b.expires_on} ${b.expires_on < todayStr ? '已过期' : '到期'} · 库存 ${b.stock}`,
          late: b.expires_on < todayStr,
        })),
      },
    )
  }
  return s.filter((k) => k.count > 0)
})

// Flat to-do list: red kinds first, then the order above; at most SHOW rows of a kind, then a link to the whole filtered list.
const SHOW = 5
// more: the "全部 N 条" line (no type in front); link: blue, the line is something to do rather than an item
type Line = Row & { type: string; alert?: boolean; more?: boolean; link?: boolean }
const lines = computed<Line[]>(() =>
  [...kinds.value.filter((k) => k.alert), ...kinds.value.filter((k) => !k.alert)].flatMap((k): Line[] => {
    const head = { type: k.type, alert: k.alert }
    if (k.action) return [{ ...head, key: k.type, to: k.action.to, text: k.action.label, link: true }]
    if (k.names) return [{ ...head, key: k.type, to: k.to, text: k.names.join('、'), hint: k.hint }]
    const rows = k.rows ?? []
    const shown: Line[] = rows.slice(0, SHOW).map((r) => ({ ...head, ...r, key: `${k.type}-${r.key}` }))
    if (k.count > shown.length) shown.push({ ...head, key: `${k.type}-more`, to: k.to, text: `全部 ${total(k)} 条`, more: true, link: true })
    return shown
  }),
)

// The schedule: bookings by day, each day with a tear-off date on the left; then this week's report and borrowed
// specimens. Empty parts are left out.
interface Day { key: string; month: string; day: number; weekday: string; today: boolean; rows: Row[] }
const days = computed<Day[]>(() => {
  const out: Day[] = []
  for (const b of data.value?.my.upcoming_bookings ?? []) {
    const p = formatPeriod(b.start_at, b.end_at) // "2026-11-23 09:00 – 11:00"
    const key = p.slice(0, 10)
    let d = out.find((x) => x.key === key)
    if (!d) {
      const date = new Date(`${key}T00:00:00`)
      d = { key, month: `${date.getMonth() + 1}月`, day: date.getDate(), weekday: date.toLocaleDateString('zh-CN', { weekday: 'short' }), today: key === todayStr, rows: [] }
      out.push(d)
    }
    d.rows.push({ key: b.id, to: { name: 'bookings', query: { booking: b.id } }, code: b.equipment.code, text: b.equipment.name, hint: p.slice(11) })
  }
  return out
})
const others = computed(() => {
  const my = data.value?.my
  if (!my) return []
  const groups: { title: string; rows: Row[] }[] = []
  if (my.current_week_report) {
    const r = my.current_week_report
    groups.push({ title: '本周周报', rows: [{ key: r.id, to: { name: 'report-edit', params: { id: r.id } }, text: `${r.week_start} 这一周`, status: r.status }] })
  }
  const late = data.value?.overdue_tasks ?? 0
  if (late) {
    groups.push({ title: '项目', rows: [{ key: 'overdue-tasks', to: { name: 'projects' }, text: `组里有 ${late} 个任务已逾期`, danger: '已逾期' }] })
  }
  if (my.borrowed_specimens_count) {
    const rows: Row[] = my.borrowed_specimens.map((l) => ({
      key: l.loan_id, to: { name: 'specimen-detail', params: { id: l.specimen.id } }, code: l.specimen.code, text: l.specimen.name,
      hint: l.due_date ? `到期 ${l.due_date}` : '未设到期日', danger: l.overdue ? '已逾期' : undefined,
    }))
    if (my.borrowed_specimens_count > rows.length) {
      rows.push({ key: 'more', to: { name: 'specimens', query: { mine: '1' } }, text: `全部 ${my.borrowed_specimens_count} 件` })
    }
    groups.push({ title: '我借的试件', rows })
  }
  return groups
})

// One line under the greeting; a kind listing names (未交周报) counts once.
const summary = computed(() => {
  const todo = kinds.value.reduce((n, k) => n + (k.names ? 1 : k.count), 0)
  const booked = data.value?.my.upcoming_bookings.length ?? 0
  return [todo ? `${todo} 件事等你处理` : '没有要你处理的事', booked ? `接下来 ${booked} 个预约` : ''].filter(Boolean).join(' · ')
})

// Width of the right column: drag the gap between the cards, or focus it and use ←/→; double-click resets.
// Kept per browser. Above half the row it is capped by CSS (min(…, 50%)), so a wide setting cannot squeeze the list.
const SIDE_KEY = 'lab.workbench.side'
const SIDE_DEFAULT = 400
const clampSide = (w: number) => Math.round(Math.min(720, Math.max(300, w)))
const side = ref(clampSide(Number(localStorage.getItem(SIDE_KEY)) || SIDE_DEFAULT))
const setSide = (w: number) => localStorage.setItem(SIDE_KEY, String((side.value = clampSide(w))))
function drag(e: PointerEvent) {
  const bar = e.currentTarget as HTMLElement
  const row = bar.parentElement!.getBoundingClientRect()
  bar.setPointerCapture(e.pointerId)
  // follow the pointer only as far as the CSS cap (half the row) lets the column grow
  const move = (m: PointerEvent) => (side.value = clampSide(Math.min(row.right - m.clientX - 8, row.width / 2)))
  const up = () => {
    bar.removeEventListener('pointermove', move)
    bar.removeEventListener('pointerup', up)
    setSide(side.value)
  }
  bar.addEventListener('pointermove', move)
  bar.addEventListener('pointerup', up)
}
</script>

<template>
  <div v-loading="loading" class="wb">
    <header class="wb-head">
      <div>
        <h1 class="hello">你好，{{ auth.user?.name || auth.user?.username }}</h1>
        <p class="sub">{{ today }}<template v-if="data"> · {{ summary }}</template></p>
      </div>
      <el-button v-if="!auth.isAdvisor" type="primary" :icon="Plus" @click="$router.push({ name: 'experiment-new' })">新建实验记录</el-button>
    </header>

    <!-- Left: things only you can move forward. Right: what is already booked or borrowed, to keep in mind. -->
    <div v-if="data" class="wb-cols" :style="{ '--side': `${side}px` }">
      <el-card class="card" header="需要你处理">
        <ul v-if="lines.length" class="rows">
          <li v-for="r in lines" :key="r.key">
            <RouterLink :to="r.to" class="row" :class="{ more: r.more }">
              <el-tag v-if="!r.more" class="kind" :type="r.alert ? 'danger' : 'info'" disable-transitions>{{ r.type }}</el-tag>
              <span class="main">
                <span class="title" :class="{ link: r.link }"><span v-if="r.code" class="code">{{ r.code }}</span> {{ r.text }}</span>
                <span v-if="r.hint" class="detail" :class="{ late: r.late }">{{ r.hint }}</span>
              </span>
              <StatusTag v-if="r.status" :status="r.status" />
              <el-icon class="chev" aria-hidden="true"><ArrowRight /></el-icon>
            </RouterLink>
          </li>
        </ul>
        <p v-else class="quiet">都处理完了。</p>
      </el-card>

      <div
        class="splitter"
        role="separator"
        aria-orientation="vertical"
        aria-label="拖动调整两栏宽度"
        :aria-valuenow="side"
        aria-valuemin="300"
        aria-valuemax="720"
        tabindex="0"
        @pointerdown="drag"
        @dblclick="setSide(SIDE_DEFAULT)"
        @keydown.left.prevent="setSide(side + 24)"
        @keydown.right.prevent="setSide(side - 24)"
      />

      <el-card class="card" header="接下来">
        <div v-for="d in days" :key="d.key" class="day">
          <div class="date" :class="{ today: d.today }">
            <span>{{ d.today ? '今天' : d.month }}</span>
            <b>{{ d.day }}</b>
            <span>{{ d.weekday }}</span>
          </div>
          <ul class="rows">
            <li v-for="r in d.rows" :key="r.key">
              <RouterLink :to="r.to" class="row">
                <span class="main">
                  <span class="title"><span class="code">{{ r.code }}</span> {{ r.text }}</span>
                  <span class="detail">{{ r.hint }}</span>
                </span>
              </RouterLink>
            </li>
          </ul>
        </div>
        <section v-for="g in others" :key="g.title" class="group">
          <h3 class="group-title">{{ g.title }}</h3>
          <ul class="rows">
            <li v-for="r in g.rows" :key="r.key">
              <RouterLink :to="r.to" class="row">
                <span class="main">
                  <span class="title" :class="{ link: r.key === 'more' }"><span v-if="r.code" class="code">{{ r.code }}</span> {{ r.text }}</span>
                  <span v-if="r.hint" class="detail">{{ r.hint }}</span>
                </span>
                <StatusTag v-if="r.status" :status="r.status" />
                <el-tag v-if="r.danger" class="status-tag" type="danger" disable-transitions>{{ r.danger }}</el-tag>
              </RouterLink>
            </li>
          </ul>
        </section>
        <p v-if="!days.length && !others.length" class="quiet">近期没有预约。</p>
      </el-card>
    </div>
  </div>
</template>

<style scoped>
.wb {
  min-height: 200px;
}
.wb-head {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 20px;
}
.hello {
  margin: 0;
  font-size: 24px;
  font-weight: 600;
  letter-spacing: -0.01em;
}
.sub {
  margin: 4px 0 0;
  color: var(--lab-text-3);
}
.wb-cols {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 16px min(var(--side), 50%);
  row-gap: 16px;
  align-items: start;
}
/* The gap between the cards is the handle: a short bar shows on hover, focus or while dragging. */
.splitter {
  align-self: stretch;
  position: relative;
  cursor: col-resize;
  touch-action: none;
  outline: none;
}
.splitter::after {
  content: '';
  position: absolute;
  top: 24px;
  left: 6px;
  width: 4px;
  height: 48px;
  border-radius: 999px;
  background: transparent;
}
.splitter:hover::after,
.splitter:focus-visible::after,
.splitter:active::after {
  background: var(--el-color-primary-light-5);
}
.wb-cols > .card {
  margin-top: 0;
}
/* Rows are whole links: two lines (what, then the detail), a rounded highlight on hover, no rules between them. */
.rows {
  margin: 0 -10px;
  padding: 0;
  list-style: none;
}
.row {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 9px 10px;
  border-radius: 12px;
  color: var(--lab-text);
}
.row:hover {
  background: var(--lab-bg);
  text-decoration: none;
}
.kind {
  flex: none;
  width: 92px;
  justify-content: center;
}
.main {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.title {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.title.link {
  color: var(--lab-link);
}
.row.more .main {
  padding-left: 104px; /* under the titles, past the kind pills */
}
.detail {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--lab-text-3);
  font-size: 13px;
}
.detail.late {
  color: var(--el-color-danger);
}
.chev {
  flex: none;
  color: var(--lab-text-3);
}
.day {
  display: flex;
  align-items: flex-start;
  gap: 8px;
}
.day + .day {
  margin-top: 10px;
}
.day .rows {
  flex: 1;
  min-width: 0;
  margin-left: 0;
}
.date {
  flex: none;
  display: flex;
  flex-direction: column;
  align-items: center;
  width: 52px;
  padding: 6px 0;
  border-radius: 12px;
  background: var(--lab-bg);
  line-height: 1.3;
}
.date span {
  color: var(--lab-text-3);
  font-size: 13px;
}
.date b {
  font-size: 20px;
  font-weight: 600;
}
.date.today {
  background: var(--el-color-primary);
  color: #fff;
}
.date.today span {
  color: #fff;
}
.group {
  margin-top: 16px;
}
.group-title {
  margin: 0 0 2px;
  color: var(--lab-text-3);
  font-size: 13px;
  font-weight: 500;
}
.quiet {
  margin: 0;
  color: var(--lab-text-2);
}
@media (max-width: 1000px) {
  .wb-cols {
    grid-template-columns: minmax(0, 1fr);
  }
  .splitter {
    display: none;
  }
}
@media (max-width: 768px) {
  .wb-head {
    flex-direction: column;
    align-items: flex-start;
  }
  .kind {
    width: auto;
  }
  .row.more .main {
    padding-left: 0;
  }
}
</style>

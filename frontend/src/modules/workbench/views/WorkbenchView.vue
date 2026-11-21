<script setup lang="ts">
import { computed, ref } from 'vue'
import type { RouteLocationRaw } from 'vue-router'
import { Plus } from '@element-plus/icons-vue'
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
        type: '待反馈周报', count: sv.pending_reviews.length, to: { name: 'reports' }, alert: true,
        rows: sv.pending_reviews.map((r) => ({
          key: r.id, to: { name: 'report-edit', params: { id: r.id } }, text: `${r.owner.name} · ${r.week_start} 这一周`, status: r.status,
        })),
      },
      { type: '未交周报', count: sv.missing_reports.length, to: { name: 'reports' }, names: sv.missing_reports.map((u) => u.name), hint: `${sv.week_start} 这一周` },
    )
  }
  const my = d.my
  s.push({
    type: '采购被退回', count: my.returned_purchases.length, to: { name: 'purchases' }, alert: true,
    rows: my.returned_purchases.map((p) => ({ key: p.id, to: { name: 'purchase-detail', params: { id: p.id } }, code: p.code, text: p.purpose, hint: '去修改' })),
  })
  if (!d.supervisor && !my.current_week_report) {
    s.push({ type: '本周周报', count: 1, to: { name: 'reports' }, alert: true, action: { label: '写本周周报', to: { name: 'report-new' } } })
  }
  s.push(
    {
      type: '周报需补充', count: my.reports_needing_revision.length, to: { name: 'reports' }, alert: true,
      rows: my.reports_needing_revision.map((r) => ({ key: r.id, to: { name: 'report-edit', params: { id: r.id } }, text: `${r.week_start} 这一周`, status: r.status })),
    },
    {
      type: '待登记使用', count: my.unreported_bookings.length, to: { name: 'bookings' },
      rows: my.unreported_bookings.map((b) => ({
        key: b.id, to: { name: 'bookings', query: { booking: b.id } }, code: b.equipment.code, text: formatPeriod(b.start_at, b.end_at), hint: '去登记',
      })),
    },
    {
      type: '实验未提交', count: my.draft_experiments.length, to: { name: 'experiments' },
      rows: my.draft_experiments.map((x) => ({ key: x.id, to: { name: 'experiment-edit', params: { id: x.id } }, code: x.code, text: x.title, status: x.status })),
    },
    {
      type: '行动项', count: my.action_items.length, to: { name: 'meetings' }, alert: my.action_items.some((a) => a.due_date && a.due_date < todayStr),
      rows: my.action_items.map((a) => ({
        key: a.id, to: { name: 'meeting-detail', params: { id: a.meeting.id } }, text: a.content,
        hint: a.due_date ? `${a.due_date} 截止` : `${a.meeting.date} 组会`, late: !!a.due_date && a.due_date < todayStr,
      })),
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
        type: '逾期未还', count: m.overdue_loans_count, to: { name: 'specimens', query: { overdue: '1' } }, alert: true,
        rows: m.overdue_loans.map((l) => ({
          key: l.loan_id, to: { name: 'specimen-detail', params: { id: l.specimen.id } }, code: l.specimen.code, text: l.specimen.name,
          hint: `${l.borrower.name} · 到期 ${l.due_date}`,
        })),
      },
      {
        type: '设备待检查', count: m.equipment_to_check.length, to: { name: 'equipment', query: { status: 'needs_check' } }, alert: true,
        rows: m.equipment_to_check.map((e) => ({ key: e.id, to: { name: 'equipment-detail', params: { id: e.id } }, code: e.code, text: e.name, status: e.status })),
      },
      {
        type: '校准到期', count: m.calibration_due_count, to: { name: 'equipment', query: { calibration_within: '30' } },
        rows: m.calibration_due.map((e) => ({
          key: e.id, to: { name: 'equipment-detail', params: { id: e.id } }, code: e.code, text: e.name, hint: `${e.calibration_due} 到期`,
          late: e.calibration_due < todayStr,
        })),
      },
      {
        type: '库存不足', count: m.low_stock.length, to: { name: 'consumables' },
        rows: m.low_stock.map((c) => ({ key: c.id, to: { name: 'consumables' }, text: `${c.name} ${c.spec}`, hint: `剩 ${c.stock} ${c.unit} / 安全库存 ${c.safety_stock}` })),
      },
      {
        type: '批次将到期', count: m.expiring_batches?.length ?? 0, to: { name: 'consumables', query: { expiring_within: '30' } },
        rows: (m.expiring_batches ?? []).map((b) => ({
          key: b.id, to: { name: 'consumables', query: { expiring_within: '30' } }, text: `${b.consumable__name} · ${b.batch_no}`,
          hint: `${b.expires_on} 到期 · 库存 ${b.stock}`,
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

// The schedule: this week's report, bookings grouped by day, borrowed specimens. Empty groups are left out.
const day = (d: string) => {
  const w = new Date(`${d}T00:00:00`).toLocaleDateString('zh-CN', { month: 'numeric', day: 'numeric', weekday: 'short' })
  return d === todayStr ? `今天 · ${w}` : w
}
const agenda = computed(() => {
  const d = data.value
  if (!d) return []
  const my = d.my
  const groups: { title: string; rows: Row[] }[] = []
  if (my.current_week_report) {
    const r = my.current_week_report
    groups.push({ title: '本周周报', rows: [{ key: r.id, to: { name: 'report-edit', params: { id: r.id } }, text: `${r.week_start} 这一周`, status: r.status }] })
  }
  for (const b of my.upcoming_bookings) {
    const p = formatPeriod(b.start_at, b.end_at) // "2026-11-23 09:00 – 11:00"
    const title = day(p.slice(0, 10))
    const row = { key: b.id, to: { name: 'bookings', query: { booking: b.id } }, lead: p.slice(11), code: b.equipment.code, text: b.equipment.name }
    const g = groups.find((x) => x.title === title)
    if (g) g.rows.push(row)
    else groups.push({ title, rows: [row] })
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
</script>

<template>
  <div v-loading="loading" class="wb">
    <header class="wb-head">
      <div>
        <h1 class="hello">你好，{{ auth.user?.name || auth.user?.username }}。</h1>
        <p class="sub">{{ today }}</p>
      </div>
      <el-button v-if="!auth.isSupervisor" :icon="Plus" @click="$router.push({ name: 'experiment-new' })">新建实验记录</el-button>
    </header>

    <div v-if="data" class="wb-cols">
      <el-card class="card" header="要处理">
        <ul v-if="lines.length" class="list">
          <li v-for="r in lines" :key="r.key">
            <span class="type" :class="{ alert: r.alert }">{{ r.more ? '' : r.type }}</span>
            <RouterLink :to="r.to" class="text" :class="{ link: r.link }"><span v-if="r.code" class="code">{{ r.code }}</span> {{ r.text }}</RouterLink>
            <StatusTag v-if="r.status" :status="r.status" />
            <span v-if="r.hint" class="hint" :class="{ late: r.late }">{{ r.hint }}</span>
          </li>
        </ul>
        <p v-else class="quiet">都处理完了。</p>
      </el-card>

      <el-card class="card" header="我的日程">
        <section v-for="g in agenda" :key="g.title" class="group">
          <h3 class="group-title">{{ g.title }}</h3>
          <ul class="list">
            <li v-for="r in g.rows" :key="r.key">
              <span v-if="r.lead" class="lead">{{ r.lead }}</span>
              <RouterLink :to="r.to" class="text"><span v-if="r.code" class="code">{{ r.code }}</span> {{ r.text }}</RouterLink>
              <StatusTag v-if="r.status" :status="r.status" />
              <span v-if="r.hint" class="hint">{{ r.hint }}</span>
              <el-tag v-if="r.danger" type="danger" size="small" disable-transitions>{{ r.danger }}</el-tag>
            </li>
          </ul>
        </section>
        <p v-if="!agenda.length" class="quiet">近期没有预约。</p>
      </el-card>
    </div>
  </div>
</template>

<style scoped>
/* A to-do list reads along a line: keep it narrow enough that the hint stays near its item (DESIGN.md). */
.wb {
  max-width: 1120px;
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
  font-size: 22px;
  font-weight: 600;
  letter-spacing: -0.01em;
}
.sub {
  margin: 4px 0 0;
  color: var(--lab-text-2);
  font-size: 14px;
}
.wb-cols {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 360px;
  gap: 16px;
  align-items: start;
}
.wb-cols > .card {
  margin-top: 0;
}
.list {
  margin: 0;
  padding: 0;
  list-style: none;
}
.list li {
  display: flex;
  align-items: center;
  gap: 12px;
  min-height: 40px;
  border-bottom: 1px solid var(--lab-border);
}
.list li:last-child {
  border-bottom: none;
}
.type {
  flex: none;
  width: 6em;
  color: var(--lab-text-2);
}
.type.alert {
  color: var(--el-color-danger);
}
.lead {
  flex: none;
  min-width: 8.5em;
  color: var(--lab-text-2);
  font-variant-numeric: tabular-nums;
}
.text {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--lab-text);
}
.text:hover,
.text.link {
  color: var(--lab-link);
}
.hint {
  flex: none;
  color: var(--lab-text-2);
}
.hint.late {
  color: var(--el-color-danger);
}
.group + .group {
  margin-top: 16px;
}
.group-title {
  margin: 0 0 2px;
  font-size: 14px;
  font-weight: 600;
}
.quiet {
  margin: 0;
  color: var(--lab-text-2);
}
@media (max-width: 1000px) {
  .wb-cols {
    grid-template-columns: minmax(0, 1fr);
  }
}
@media (max-width: 768px) {
  .wb-head {
    flex-direction: column;
    align-items: flex-start;
  }
  .list li {
    flex-wrap: wrap;
    gap: 4px 12px;
    padding: 8px 0;
  }
}
</style>

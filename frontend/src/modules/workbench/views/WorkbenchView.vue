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

// One line in a section: a link on the left; on the right a hint, a status tag or a red tag.
interface Row { key: string | number; to: RouteLocationRaw; code?: string; text: string; hint?: string; late?: boolean; status?: string; danger?: string }
// A section's heading links to the matching filtered list and shows the real total (the API sends at most 20 rows).
interface Section {
  title: string
  count: number
  to: RouteLocationRaw
  alert?: boolean
  rows?: Row[]
  names?: string[] // shown as tags, e.g. who has not handed in this week's report
  action?: { label: string; to: RouteLocationRaw } // nothing to list, one thing to do
}
const label = (s: Section) => (s.action ? '未写' : s.rows && s.rows.length >= 20 && s.count <= 20 ? '20+' : String(s.count))

// The workbench answers "what needs me now" (DESIGN.md): sections with something in them, most urgent first.
const todo = computed<Section[]>(() => {
  const d = data.value
  if (!d) return []
  const s: Section[] = []
  if (d.supervisor) {
    const sv = d.supervisor
    s.push(
      {
        title: '待我审批的采购', count: sv.purchases_to_review.length, to: { name: 'purchase-reviews' }, alert: true,
        rows: sv.purchases_to_review.map((p) => ({
          key: p.id, to: { name: 'purchase-detail', params: { id: p.id }, query: { from: 'reviews' } },
          code: p.code, text: `${p.owner.name} · ${p.purpose}`, hint: `¥ ${formatMoney(p.total)}`,
        })),
      },
      {
        title: '待反馈的周报', count: sv.pending_reviews.length, to: { name: 'reports' }, alert: true,
        rows: sv.pending_reviews.map((r) => ({
          key: r.id, to: { name: 'report-edit', params: { id: r.id } }, text: `${r.owner.name} · ${r.week_start} 这一周`, status: r.status,
        })),
      },
      { title: `本周未交周报（${sv.week_start} 这一周）`, count: sv.missing_reports.length, to: { name: 'reports' }, names: sv.missing_reports.map((u) => u.name) },
    )
  }
  const my = d.my
  s.push({
    title: '被退回的采购', count: my.returned_purchases.length, to: { name: 'purchases' }, alert: true,
    rows: my.returned_purchases.map((p) => ({ key: p.id, to: { name: 'purchase-detail', params: { id: p.id } }, code: p.code, text: p.purpose, hint: '去修改' })),
  })
  if (!d.supervisor && !my.current_week_report) {
    s.push({ title: '本周周报', count: 1, to: { name: 'reports' }, alert: true, action: { label: '写本周周报', to: { name: 'report-new' } } })
  }
  s.push(
    {
      title: '需补充的周报', count: my.reports_needing_revision.length, to: { name: 'reports' }, alert: true,
      rows: my.reports_needing_revision.map((r) => ({ key: r.id, to: { name: 'report-edit', params: { id: r.id } }, text: `${r.week_start} 这一周`, status: r.status })),
    },
    {
      title: '待登记使用结果', count: my.unreported_bookings.length, to: { name: 'bookings' },
      rows: my.unreported_bookings.map((b) => ({
        key: b.id, to: { name: 'bookings', query: { booking: b.id } }, code: b.equipment.code, text: formatPeriod(b.start_at, b.end_at), hint: '去登记',
      })),
    },
    {
      title: '未提交的实验记录', count: my.draft_experiments.length, to: { name: 'experiments' },
      rows: my.draft_experiments.map((x) => ({ key: x.id, to: { name: 'experiment-edit', params: { id: x.id } }, code: x.code, text: x.title, status: x.status })),
    },
    {
      title: '我的行动项', count: my.action_items.length, to: { name: 'meetings' }, alert: my.action_items.some((a) => a.due_date && a.due_date < todayStr),
      rows: my.action_items.map((a) => ({
        key: a.id, to: { name: 'meeting-detail', params: { id: a.meeting.id } }, text: a.content,
        hint: a.due_date ? `${a.due_date} 截止` : `${a.meeting.date} 组会`, late: !!a.due_date && a.due_date < todayStr,
      })),
    },
    {
      title: '我的任务', count: my.tasks?.length ?? 0, to: { name: 'projects' },
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
        title: '逾期未还', count: m.overdue_loans_count, to: { name: 'specimens', query: { overdue: '1' } }, alert: true,
        rows: m.overdue_loans.map((l) => ({
          key: l.loan_id, to: { name: 'specimen-detail', params: { id: l.specimen.id } }, code: l.specimen.code, text: l.specimen.name,
          hint: `${l.borrower.name} · 到期 ${l.due_date}`,
        })),
      },
      {
        title: '待检查的设备', count: m.equipment_to_check.length, to: { name: 'equipment', query: { status: 'needs_check' } }, alert: true,
        rows: m.equipment_to_check.map((e) => ({ key: e.id, to: { name: 'equipment-detail', params: { id: e.id } }, code: e.code, text: e.name, status: e.status })),
      },
      {
        title: '校准到期', count: m.calibration_due_count, to: { name: 'equipment', query: { calibration_within: '30' } },
        rows: m.calibration_due.map((e) => ({
          key: e.id, to: { name: 'equipment-detail', params: { id: e.id } }, code: e.code, text: e.name, hint: `校准到期 ${e.calibration_due}`,
          late: e.calibration_due < todayStr,
        })),
      },
      {
        title: '库存不足的耗材', count: m.low_stock.length, to: { name: 'consumables' },
        rows: m.low_stock.map((c) => ({ key: c.id, to: { name: 'consumables' }, text: `${c.name} ${c.spec}`, hint: `剩 ${c.stock} ${c.unit} / 安全库存 ${c.safety_stock}` })),
      },
      {
        title: '30 天内到期的耗材批次', count: m.expiring_batches?.length ?? 0, to: { name: 'consumables', query: { expiring_within: '30' } },
        rows: (m.expiring_batches ?? []).map((b) => ({
          key: b.id, to: { name: 'consumables', query: { expiring_within: '30' } }, text: `${b.consumable__name} · ${b.batch_no}`,
          hint: `${b.expires_on} 到期 · 库存 ${b.stock}`,
        })),
      },
    )
  }
  return s
})

// Advisors and managers do little bench work: their own sections appear only when there is something in them.
const ownOnly = new Set(['被退回的采购', '需补充的周报', '待登记使用结果', '未提交的实验记录', '我的行动项', '我的任务'])
const pending = computed(() => todo.value.filter((s) => s.count > 0))
const cleared = computed(() =>
  todo.value.filter((s) => s.count === 0 && !(ownOnly.has(s.title) && data.value?.supervisor)).map((s) => s.title.replace(/（.*）/, '')),
)

const agenda = computed<Section[]>(() => {
  const d = data.value
  if (!d) return []
  const my = d.my
  const s: Section[] = []
  if (my.current_week_report) {
    const r = my.current_week_report
    s.push({ title: '本周周报', count: 1, to: { name: 'reports' }, rows: [{ key: r.id, to: { name: 'report-edit', params: { id: r.id } }, text: `${r.week_start} 这一周`, status: r.status }] })
  }
  s.push(
    {
      title: '我的预约', count: my.upcoming_bookings.length, to: { name: 'bookings' },
      rows: my.upcoming_bookings.map((b) => ({
        key: b.id, to: { name: 'bookings', query: { booking: b.id } }, code: b.equipment.code, text: b.equipment.name, hint: formatPeriod(b.start_at, b.end_at),
      })),
    },
    {
      title: '我借的试件', count: my.borrowed_specimens_count, to: { name: 'specimens', query: { mine: '1' } }, alert: my.borrowed_specimens.some((l) => l.overdue),
      rows: my.borrowed_specimens.map((l) => ({
        key: l.loan_id, to: { name: 'specimen-detail', params: { id: l.specimen.id } }, code: l.specimen.code, text: l.specimen.name,
        hint: l.due_date ? `到期 ${l.due_date}` : '未设到期日', danger: l.overdue ? '已逾期' : undefined,
      })),
    },
  )
  return s
})
</script>

<template>
  <div v-loading="loading" class="wb">
    <header class="wb-head">
      <div>
        <h1 class="hello">你好，{{ auth.user?.name || auth.user?.username }}。</h1>
        <p class="sub">{{ today }}<template v-if="data"> · {{ pending.length ? `${pending.length} 类事情等你处理` : '没有要你处理的事' }}</template></p>
      </div>
      <el-button v-if="!auth.isSupervisor" :icon="Plus" @click="$router.push({ name: 'experiment-new' })">新建实验记录</el-button>
    </header>

    <div v-if="data" class="wb-cols">
      <el-card class="card" header="要处理">
        <section v-for="s in pending" :key="s.title" class="sec">
          <RouterLink :to="s.to" class="sec-head">
            <span>{{ s.title }}</span>
            <span class="count" :class="{ alert: s.alert }">{{ label(s) }}</span>
          </RouterLink>
          <el-button v-if="s.action" type="primary" size="small" class="sec-action" @click="$router.push(s.action.to)">{{ s.action.label }}</el-button>
          <div v-if="s.names" class="actions names">
            <el-tag v-for="n in s.names" :key="n" type="danger" disable-transitions>{{ n }}</el-tag>
          </div>
          <ul v-if="s.rows?.length" class="rows">
            <li v-for="r in s.rows" :key="r.key">
              <RouterLink :to="r.to"><span v-if="r.code" class="code">{{ r.code }}</span> {{ r.text }}</RouterLink>
              <span class="right">
                <StatusTag v-if="r.status" :status="r.status" />
                <span v-if="r.hint" class="hint" :class="{ late: r.late }">{{ r.hint }}</span>
              </span>
            </li>
          </ul>
        </section>
        <p v-if="!pending.length" class="all-clear">都处理完了。</p>
        <p v-if="cleared.length" class="cleared">没有待处理：{{ cleared.join('、') }}</p>
      </el-card>

      <el-card class="card" header="我的日程">
        <section v-for="s in agenda" :key="s.title" class="sec">
          <RouterLink :to="s.to" class="sec-head">
            <span>{{ s.title }}</span>
            <span class="count" :class="{ alert: s.alert }">{{ label(s) }}</span>
          </RouterLink>
          <ul v-if="s.rows?.length" class="rows">
            <li v-for="r in s.rows" :key="r.key" class="stacked">
              <RouterLink :to="r.to"><span v-if="r.code" class="code">{{ r.code }}</span> {{ r.text }}</RouterLink>
              <span class="right">
                <StatusTag v-if="r.status" :status="r.status" />
                <span v-if="r.hint" class="hint">{{ r.hint }}</span>
                <el-tag v-if="r.danger" type="danger" size="small" disable-transitions>{{ r.danger }}</el-tag>
              </span>
            </li>
          </ul>
          <p v-else class="cleared">暂无</p>
        </section>
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
  font-size: 22px;
  font-weight: 600;
  letter-spacing: -0.01em;
}
.sub {
  margin: 4px 0 0;
  color: var(--lab-text-3);
  font-size: 13px;
}
.wb-cols {
  display: grid;
  grid-template-columns: minmax(0, 2fr) minmax(300px, 1fr);
  gap: 16px;
  align-items: start;
}
.wb-cols > .card {
  margin-top: 0;
}
.sec + .sec {
  margin-top: 20px;
}
.sec-head {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
  color: var(--lab-text);
  font-weight: 600;
}
.count {
  min-width: 22px;
  padding: 0 7px;
  border-radius: 999px;
  background: var(--el-fill-color);
  color: var(--lab-text-2);
  font-size: 13px;
  font-weight: 600;
  line-height: 22px;
  text-align: center;
  font-variant-numeric: tabular-nums;
}
.count.alert {
  background: var(--el-color-danger-light-9);
  color: var(--el-color-danger);
}
.sec-action {
  display: block;
  margin-top: 2px;
}
.names {
  margin-top: 2px;
}
.rows {
  margin: 0;
  padding: 0;
  list-style: none;
  border-top: 1px solid var(--lab-border);
}
.rows li {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 8px 4px;
  border-bottom: 1px solid var(--lab-border);
}
.rows li.stacked {
  flex-direction: column;
  align-items: flex-start;
  gap: 2px;
}
.rows a {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--lab-text);
}
.rows a:hover {
  color: var(--lab-link);
}
.right {
  flex: none;
  display: inline-flex;
  align-items: center;
  gap: 8px;
}
.hint {
  color: var(--lab-text-3);
  font-size: 13px;
}
.hint.late {
  color: var(--el-color-danger);
}
.all-clear {
  margin: 0;
  font-size: 15px;
}
.cleared {
  margin: 16px 0 0;
  color: var(--lab-text-3);
  font-size: 13px;
}
.sec .cleared {
  margin: 0;
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
}
</style>

<script setup lang="ts">
import { computed, ref } from 'vue'
import type { RouteLocationRaw } from 'vue-router'
import { Plus } from '@element-plus/icons-vue'
import { dashboardApi } from '@/modules/workbench/api'
import type { Dashboard } from '@/api/types'
import { useAuthStore } from '@/stores/auth'
import { STATUS, formatMoney, formatPeriod, toDateStr } from '@/utils/format'
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

// The API returns at most 20 items per list (workbench/views.py LIMIT).
const n = (list: unknown[]) => (list.length >= 20 ? '20+' : String(list.length))

const tiles = computed(() => {
  const d = data.value
  if (!d) return []
  const result: { label: string; value: string; to: RouteLocationRaw; alert?: boolean }[] = []
  if (d.supervisor) {
    result.push(
      { label: '待反馈的周报', value: n(d.supervisor.pending_reviews), to: { name: 'reports' }, alert: d.supervisor.pending_reviews.length > 0 },
      { label: '本周未交', value: n(d.supervisor.missing_reports), to: { name: 'reports' } },
      {
        label: '待我审批的采购',
        value: n(d.supervisor.purchases_to_review),
        to: { name: 'purchase-reviews' },
        alert: d.supervisor.purchases_to_review.length > 0,
      },
    )
  } else {
    const current = d.my.current_week_report
    result.push({
      label: '本周周报',
      value: current ? STATUS[current.status]?.label ?? current.status : '未写',
      to: current ? { name: 'report-edit', params: { id: current.id } } : { name: 'report-new' },
      alert: !current,
    })
  }
  if (!d.supervisor || d.my.reports_needing_revision.length) {
    result.push({ label: '需补充的周报', value: n(d.my.reports_needing_revision), to: { name: 'reports' }, alert: d.my.reports_needing_revision.length > 0 })
  }
  if (!d.supervisor || d.my.draft_experiments.length) {
    result.push({ label: '未提交的实验记录', value: n(d.my.draft_experiments), to: { name: 'experiments' } })
  }
  if (d.my.action_items.length) {
    const late = d.my.action_items.some((a) => a.due_date && a.due_date < todayStr)
    result.push({ label: '我的行动项', value: n(d.my.action_items), to: { name: 'meetings' }, alert: late })
  }
  if (d.my.returned_purchases.length) {
    result.push({ label: '被退回的采购', value: n(d.my.returned_purchases), to: { name: 'purchases' }, alert: true })
  }
  if (!d.supervisor || d.my.upcoming_bookings.length) {
    result.push({ label: '我的预约', value: n(d.my.upcoming_bookings), to: { name: 'bookings' } })
  }
  if (d.manager) {
    result.push(
      { label: '待检查的设备', value: n(d.manager.equipment_to_check), to: { name: 'equipment', query: { status: 'needs_check' } }, alert: d.manager.equipment_to_check.length > 0 },
      { label: '库存不足的耗材', value: n(d.manager.low_stock), to: { name: 'consumables' }, alert: d.manager.low_stock.length > 0 },
    )
  }
  return result
})

// Supervisors see their own cards only when they have items in them.
const showMine = (list: unknown[]) => !data.value?.supervisor || list.length > 0
</script>

<template>
  <div v-loading="loading" class="wb">
    <div class="wb-head">
      <div>
        <h1 class="hello">你好，{{ auth.user?.name || auth.user?.username }}。</h1>
        <div class="sub">{{ auth.user?.group?.name }} · {{ today }}</div>
      </div>
      <el-button v-if="!auth.isSupervisor" :icon="Plus" @click="$router.push({ name: 'experiment-new' })">新建实验记录</el-button>
    </div>

    <template v-if="data">
      <div class="tiles">
        <RouterLink v-for="t in tiles" :key="t.label" :to="t.to" class="tile" :class="{ alert: t.alert }">
          <span class="tile-label">{{ t.label }}</span>
          <span class="tile-value">{{ t.value }}</span>
        </RouterLink>
      </div>

      <div class="grid">
        <el-card v-if="data.supervisor" header="待反馈的周报" class="wb-card">
          <el-empty v-if="!data.supervisor.pending_reviews.length" :image-size="40" description="没有待反馈的周报" />
          <ul v-else class="rows">
            <li v-for="r in data.supervisor.pending_reviews" :key="r.id">
              <RouterLink :to="{ name: 'report-edit', params: { id: r.id } }">{{ r.owner.name }} · {{ r.week_start }} 这一周</RouterLink>
              <StatusTag :status="r.status" />
            </li>
          </ul>
        </el-card>
        <el-card v-if="data.supervisor" :header="`本周未交名单（${data.supervisor.week_start} 这一周）`" class="wb-card">
          <el-empty v-if="!data.supervisor.missing_reports.length" :image-size="40" description="本周周报已全部提交" />
          <div v-else class="actions">
            <el-tag v-for="u in data.supervisor.missing_reports" :key="u.id" type="danger" disable-transitions>{{ u.name }}</el-tag>
          </div>
        </el-card>

        <el-card v-if="data.supervisor" header="待我审批的采购" class="wb-card">
          <el-empty v-if="!data.supervisor.purchases_to_review.length" :image-size="40" description="没有等你审批的采购申请" />
          <ul v-else class="rows">
            <li v-for="p in data.supervisor.purchases_to_review" :key="p.id">
              <RouterLink :to="{ name: 'purchase-detail', params: { id: p.id }, query: { from: 'reviews' } }">
                <span class="code">{{ p.code }}</span> {{ p.owner.name }} · {{ p.purpose }}
              </RouterLink>
              <span class="hint">¥ {{ formatMoney(p.total) }}</span>
            </li>
          </ul>
        </el-card>
        <el-card v-if="data.my.action_items.length" header="我的行动项" class="wb-card">
          <ul class="rows">
            <li v-for="a in data.my.action_items" :key="a.id">
              <RouterLink :to="{ name: 'meeting-detail', params: { id: a.meeting.id } }">{{ a.content }}</RouterLink>
              <span class="hint" :class="{ late: a.due_date && a.due_date < todayStr }">
                {{ a.due_date ? `${a.due_date} 截止` : `${a.meeting.date} 组会` }}
              </span>
            </li>
          </ul>
        </el-card>

        <el-card v-if="data.my.returned_purchases.length" header="被退回的采购" class="wb-card">
          <ul class="rows">
            <li v-for="p in data.my.returned_purchases" :key="p.id">
              <RouterLink :to="{ name: 'purchase-detail', params: { id: p.id } }"><span class="code">{{ p.code }}</span> {{ p.purpose }}</RouterLink>
              <span class="hint">去修改</span>
            </li>
          </ul>
        </el-card>

        <el-card v-if="!data.supervisor || data.my.current_week_report" header="本周周报" class="wb-card">
          <ul v-if="data.my.current_week_report" class="rows">
            <li>
              <RouterLink :to="{ name: 'report-edit', params: { id: data.my.current_week_report.id } }">
                {{ data.my.current_week_report.week_start }} 这一周
              </RouterLink>
              <StatusTag :status="data.my.current_week_report.status" />
            </li>
          </ul>
          <el-button v-else type="primary" @click="$router.push({ name: 'report-new' })">写本周周报</el-button>
        </el-card>
        <el-card v-if="showMine(data.my.reports_needing_revision)" header="需补充的周报" class="wb-card">
          <el-empty v-if="!data.my.reports_needing_revision.length" :image-size="40" description="没有需要补充的周报" />
          <ul v-else class="rows">
            <li v-for="r in data.my.reports_needing_revision" :key="r.id">
              <RouterLink :to="{ name: 'report-edit', params: { id: r.id } }">{{ r.week_start }} 这一周</RouterLink>
              <StatusTag :status="r.status" />
            </li>
          </ul>
        </el-card>
        <el-card v-if="showMine(data.my.draft_experiments)" header="未提交的实验记录" class="wb-card">
          <el-empty v-if="!data.my.draft_experiments.length" :image-size="40" description="没有未提交的实验记录" />
          <ul v-else class="rows">
            <li v-for="x in data.my.draft_experiments" :key="x.id">
              <RouterLink :to="{ name: 'experiment-edit', params: { id: x.id } }">
                <span class="code">{{ x.code }}</span> {{ x.title }}
              </RouterLink>
              <StatusTag :status="x.status" />
            </li>
          </ul>
        </el-card>

        <el-card v-if="data.my.unreported_bookings.length" header="待登记使用结果" class="wb-card">
          <ul class="rows">
            <li v-for="b in data.my.unreported_bookings" :key="b.id">
              <RouterLink :to="{ name: 'bookings', query: { booking: b.id } }">
                <span class="code">{{ b.equipment.code }}</span> {{ formatPeriod(b.start_at, b.end_at) }}
              </RouterLink>
              <span class="hint">去登记</span>
            </li>
          </ul>
        </el-card>
        <el-card v-if="showMine(data.my.upcoming_bookings)" header="我的预约" class="wb-card">
          <el-empty v-if="!data.my.upcoming_bookings.length" :image-size="40" description="没有接下来的预约" />
          <ul v-else class="rows">
            <li v-for="b in data.my.upcoming_bookings" :key="b.id">
              <RouterLink :to="{ name: 'bookings', query: { booking: b.id } }">
                <span class="code">{{ b.equipment.code }}</span> {{ b.equipment.name }}
              </RouterLink>
              <span class="hint">{{ formatPeriod(b.start_at, b.end_at) }}</span>
            </li>
          </ul>
        </el-card>

        <el-card v-if="data.manager" header="待检查的设备" class="wb-card">
          <el-empty v-if="!data.manager.equipment_to_check.length" :image-size="40" description="没有待检查的设备" />
          <ul v-else class="rows">
            <li v-for="e in data.manager.equipment_to_check" :key="e.id">
              <RouterLink :to="{ name: 'equipment-detail', params: { id: e.id } }">
                <span class="code">{{ e.code }}</span> {{ e.name }}
              </RouterLink>
              <StatusTag :status="e.status" />
            </li>
          </ul>
        </el-card>
        <el-card v-if="data.manager" header="库存不足的耗材" class="wb-card">
          <el-empty v-if="!data.manager.low_stock.length" :image-size="40" description="耗材库存充足" />
          <ul v-else class="rows">
            <li v-for="c in data.manager.low_stock" :key="c.id">
              <RouterLink :to="{ name: 'consumables' }">{{ c.name }} {{ c.spec }}</RouterLink>
              <span class="hint">剩 {{ c.stock }} {{ c.unit }} / 安全库存 {{ c.safety_stock }}</span>
            </li>
          </ul>
        </el-card>
      </div>
    </template>
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
  margin-top: 4px;
  color: var(--el-text-color-secondary);
  font-size: 13px;
}
.tiles {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(170px, 1fr));
  gap: 12px;
  margin-bottom: 20px;
}
.tile {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 14px 16px;
  border: 1px solid var(--lab-border);
  border-radius: var(--lab-radius-lg);
  color: inherit;
  text-decoration: none;
  transition: border-color 0.15s, background-color 0.15s;
}
.tile:hover {
  border-color: #d4d4d4;
  background: #fcfcfc;
}
.tile-label {
  font-size: 13px;
  color: var(--el-text-color-secondary);
}
.tile-value {
  font-size: 26px;
  font-weight: 600;
  letter-spacing: -0.02em;
  line-height: 1.1;
}
.tile.alert .tile-label::after {
  content: '';
  display: inline-block;
  width: 6px;
  height: 6px;
  margin-left: 6px;
  vertical-align: middle;
  border-radius: 50%;
  background: var(--el-color-danger);
}
.grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
  gap: 16px;
}
.wb-card :deep(.el-card__body) {
  padding: 8px 12px 12px;
}
.wb-card :deep(.el-card__body) > .el-button {
  margin: 8px;
}
.wb-card :deep(.el-empty__image) {
  display: none;
}
.rows {
  margin: 0;
  padding: 0;
  list-style: none;
}
.rows li {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 8px;
  border-radius: var(--lab-radius);
}
.rows li:hover {
  background: #fafafa;
}
.hint {
  flex: none;
  color: var(--el-text-color-secondary);
  font-size: 12.5px;
}
.hint.late {
  color: var(--el-color-danger);
}
.rows a {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
@media (max-width: 768px) {
  .wb-head {
    flex-direction: column;
    align-items: flex-start;
  }
  .grid {
    grid-template-columns: 1fr;
  }
}
</style>

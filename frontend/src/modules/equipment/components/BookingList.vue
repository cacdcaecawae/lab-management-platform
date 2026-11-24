<script setup lang="ts">
import { computed, reactive } from 'vue'
import { useRoute } from 'vue-router'
import { bookingsApi } from '../api'
import type { Booking, Equipment } from '@/api/types'
import { usePagedList } from '@/composables/usePagedList'
import { BOOKING_KIND_LABELS, CONDITION_LABELS, formatPeriod } from '@/utils/format'
import PageToolbar from '@/components/PageToolbar.vue'

// The bookings page's 列表: every booking, newest first, paged (the calendar only fetches the weeks on screen).
// ?pending=1 comes from the workbench (待登记使用 → 全部).
const props = defineProps<{ equipment: Equipment[] }>()
const emit = defineEmits<{ open: [booking: Booking] }>()
const route = useRoute()
const filters = reactive({
  mine: (route.query.pending === '1' ? 1 : '') as 1 | '',
  pending: (route.query.pending === '1' ? 1 : '') as 1 | '',
  equipment: '' as number | '',
  project: (Number(route.query.project) || '') as number | '', // a project's 资产 → 全部
  from: '',
  to: '',
})
const dates = computed({
  get: () => (filters.from && filters.to ? [filters.from, filters.to] : null),
  set: (range: string[] | null) => Object.assign(filters, { from: range?.[0] ?? '', to: range?.[1] ?? '' }),
})
const { items, count, page, pageSize, loading, load } = usePagedList(bookingsApi.page, filters)
defineExpose({ load })
const toReport = (b: Booking) => b.kind === 'use' && !b.report && new Date(b.end_at).getTime() <= Date.now()
</script>

<template>
  <PageToolbar>
    <el-checkbox v-model="filters.mine" :true-value="1" false-value="">只看我的</el-checkbox>
    <el-checkbox v-model="filters.pending" :true-value="1" false-value="">待登记</el-checkbox>
    <el-select v-model="filters.equipment" placeholder="全部设备" aria-label="设备" clearable filterable>
      <el-option v-for="e in props.equipment" :key="e.id" :label="`${e.code} ${e.name}`" :value="e.id" />
    </el-select>
    <el-date-picker v-model="dates" type="daterange" value-format="YYYY-MM-DD" start-placeholder="开始日期从" end-placeholder="到" />
  </PageToolbar>
  <el-table v-loading="loading" :data="items" empty-text="暂无预约" row-class-name="clickable" @row-click="(row: Booking) => emit('open', row)">
    <el-table-column label="时间" min-width="190">
      <template #default="{ row }">
        <el-button link type="primary" @click.stop="emit('open', row as Booking)">{{ formatPeriod(row.start_at, row.end_at) }}</el-button>
      </template>
    </el-table-column>
    <el-table-column label="设备" min-width="140">
      <template #default="{ row }"><span class="code">{{ row.equipment.code }}</span> {{ row.equipment.name }}</template>
    </el-table-column>
    <el-table-column label="预约人" min-width="80">
      <template #default="{ row }">{{ row.user.name }}</template>
    </el-table-column>
    <el-table-column label="类型" min-width="70">
      <template #default="{ row }">{{ BOOKING_KIND_LABELS[row.kind] }}</template>
    </el-table-column>
    <el-table-column label="使用登记" min-width="110">
      <template #default="{ row }">
        <template v-if="row.report">{{ CONDITION_LABELS[row.report.condition] }}</template>
        <el-tag v-else-if="toReport(row as Booking)" class="status-tag" type="warning" disable-transitions>待登记</el-tag>
        <span v-if="row.planned_end_at" class="muted">提前结束</span>
      </template>
    </el-table-column>
    <el-table-column prop="purpose" label="用途" min-width="140" show-overflow-tooltip />
  </el-table>
  <el-pagination
    v-model:current-page="page"
    class="pager"
    layout="total, prev, pager, next"
    :total="count"
    :page-size="pageSize"
    hide-on-single-page
  />
</template>

<style scoped>
.muted {
  margin-left: 6px;
  color: var(--lab-text-3);
}
</style>

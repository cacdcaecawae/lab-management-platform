<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import { Download } from '@element-plus/icons-vue'
import { consumablesApi } from '@/modules/inventory/api'
import { membersApi } from '@/modules/members/api'
import { projectsApi } from '@/modules/projects/api'
import { useOptions } from '@/composables/useOptions'
import { usePagedList } from '@/composables/usePagedList'
import { useAuthStore } from '@/stores/auth'
import { TXN_KIND_LABELS, formatTime } from '@/utils/format'
import PageToolbar from '@/components/PageToolbar.vue'
import IconButton from '@/components/IconButton.vue'

// 流水: every consumable's ins and outs in one list, newest first. Advisors and managers see the group's; others see
// what they handled themselves (the API decides). The export holds exactly these rows.
const props = defineProps<{ project?: number | '' }>()
const auth = useAuthStore()
const filters = reactive({
  consumable: '' as number | '', kind: '', handler: '' as number | '', project: props.project ?? ('' as number | ''), from: '', to: '',
})
const dates = computed({
  get: () => (filters.from && filters.to ? [filters.from, filters.to] : null),
  set: (range: string[] | null) => Object.assign(filters, { from: range?.[0] ?? '', to: range?.[1] ?? '' }),
})
const { items, count, page, pageSize, loading } = usePagedList(consumablesApi.ledger, filters)
const consumables = useOptions(() => consumablesApi.list({ page_size: 100 }))
const members = auth.isSupervisor ? useOptions(() => membersApi.list({ page_size: 100 })) : ref([])
const projects = useOptions(() => projectsApi.list({ page_size: 100 }))
const KINDS = ['in', 'out', 'return', 'adjust'] as const
const signed = (n: number) => (n > 0 ? `+${n}` : String(n))
</script>

<template>
  <PageToolbar>
    <el-select v-model="filters.consumable" placeholder="全部耗材" aria-label="耗材" clearable filterable>
      <el-option v-for="c in consumables" :key="c.id" :label="`${c.name} ${c.spec}`" :value="c.id" />
    </el-select>
    <el-select v-model="filters.kind" placeholder="全部类型" aria-label="类型" clearable>
      <el-option v-for="k in KINDS" :key="k" :label="TXN_KIND_LABELS[k]" :value="k" />
    </el-select>
    <el-select v-if="auth.isSupervisor" v-model="filters.handler" placeholder="全部经手人" aria-label="经手人" clearable filterable>
      <el-option v-for="m in members" :key="m.id" :label="m.name" :value="m.id" />
    </el-select>
    <el-select v-model="filters.project" placeholder="全部项目" aria-label="项目" clearable filterable>
      <el-option v-for="p in projects" :key="p.id" :label="p.name" :value="p.id" />
    </el-select>
    <el-date-picker v-model="dates" type="daterange" value-format="YYYY-MM-DD" start-placeholder="日期从" end-placeholder="到" class="range" />
    <template #actions>
      <IconButton :icon="Download" label="导出 Excel" tag="a" :href="consumablesApi.ledgerExportUrl(filters)" />
    </template>
  </PageToolbar>
  <el-table v-loading="loading" :data="items" empty-text="暂无流水">
    <el-table-column label="时间" min-width="130">
      <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
    </el-table-column>
    <el-table-column label="耗材" min-width="140">
      <template #default="{ row }">{{ row.consumable.name }} {{ row.consumable.spec }}</template>
    </el-table-column>
    <el-table-column label="类型" min-width="80">
      <template #default="{ row }">{{ TXN_KIND_LABELS[row.kind] ?? row.kind }}</template>
    </el-table-column>
    <el-table-column label="数量" min-width="80" align="right">
      <template #default="{ row }">{{ signed(row.quantity) }} {{ row.consumable.unit }}</template>
    </el-table-column>
    <el-table-column label="批号" min-width="90">
      <template #default="{ row }">{{ row.batch?.batch_no ?? '' }}</template>
    </el-table-column>
    <el-table-column label="经手人" min-width="80">
      <template #default="{ row }">{{ row.handler.name }}</template>
    </el-table-column>
    <el-table-column label="项目" min-width="110">
      <template #default="{ row }">{{ row.project?.name ?? '' }}</template>
    </el-table-column>
    <el-table-column prop="note" label="备注" min-width="120" show-overflow-tooltip />
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
.range {
  max-width: 260px;
}
@media (max-width: 768px) {
  .range {
    width: 100%;
    max-width: none;
  }
}
</style>

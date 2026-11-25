<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { fundsApi, purchasesApi } from '@/modules/procurement/api'
import { membersApi } from '@/modules/members/api'
import { usePagedList } from '@/composables/usePagedList'
import { useLiveSearch } from '@/composables/useLiveSearch'
import { useOptions } from '@/composables/useOptions'
import { useAuthStore } from '@/stores/auth'
import { PURCHASE_STATUSES, STATUS, formatMoney, formatTime } from '@/utils/format'
import StatusTag from '@/components/StatusTag.vue'
import PageToolbar from '@/components/PageToolbar.vue'
import IconButton from '@/components/IconButton.vue'
import { Download } from '@element-plus/icons-vue'

const auth = useAuthStore()
const route = useRoute()
const router = useRouter()
// Two menu items share this page: 采购申请 (all I can see) and 我的审批 (waiting for my review).
// The view is not re-created between them, so follow the route.
const reviewing = computed(() => route.name === 'purchase-reviews')
// ?status= and ?mine=1 come from the workbench (采购草稿, 待采购, 待到货)
const routeStatus = String(route.query.status ?? '')
const filters = reactive({
  status: PURCHASE_STATUSES.includes(routeStatus as (typeof PURCHASE_STATUSES)[number]) ? routeStatus : '',
  search: '', mine: (route.query.mine === '1' ? 1 : '') as 1 | '', fund: '' as number | '', owner: '' as number | '',
  returned: ['0', '1'].includes(String(route.query.returned)) ? String(route.query.returned) : '',
  todo: (reviewing.value ? 1 : '') as 1 | '',
})
const keyword = useLiveSearch(filters)
const { items, count, page, pageSize, loading, sort } = usePagedList(purchasesApi.list, filters)
// Only managers and approvers see other people's requests, so only they filter by fund and applicant.
const funds = auth.isFinance ? useOptions(() => fundsApi.list({ page_size: 100 })) : ref([])
const members = auth.isFinance ? useOptions(() => membersApi.list({ page_size: 100 })) : ref([])

watch(reviewing, (r) => {
  Object.assign(filters, { todo: r ? 1 : '', status: '', mine: '', fund: '', owner: '', returned: '', search: '' })
  keyword.value = ''
})

// from=reviews: the detail page's back button returns to 我的审批
const detail = (id: number) => ({ name: 'purchase-detail', params: { id }, query: reviewing.value ? { from: 'reviews' } : {} })
const open = (id: number) => router.push(detail(id))
</script>

<template>
  <el-card class="card">
    <PageToolbar>
      <el-input v-model="keyword" placeholder="搜索用途、品名、申请人" clearable @change="filters.search = keyword" />
      <el-select v-if="!reviewing" v-model="filters.status" placeholder="全部状态" clearable aria-label="状态">
        <el-option v-for="s in PURCHASE_STATUSES" :key="s" :label="STATUS[s].label" :value="s" />
      </el-select>
      <el-select v-if="auth.isFinance" v-model="filters.fund" placeholder="全部经费" clearable filterable aria-label="经费来源">
        <el-option v-for="f in funds" :key="f.id" :label="`${f.code} ${f.name}`" :value="f.id" />
      </el-select>
      <el-select v-if="auth.isFinance" v-model="filters.owner" placeholder="全部申请人" clearable filterable aria-label="申请人">
        <el-option v-for="m in members" :key="m.id" :label="m.name" :value="m.id" />
      </el-select>
      <el-checkbox v-if="!reviewing && auth.isFinance" v-model="filters.mine" :true-value="1" false-value="">只看我的</el-checkbox>
      <el-select v-if="!reviewing" v-model="filters.returned" placeholder="退回与否" clearable aria-label="退回">
        <el-option label="被退回" value="1" />
        <el-option label="没被退回" value="0" />
      </el-select>
      <template #actions>
        <IconButton :icon="Download" label="导出 Excel" tag="a" :href="purchasesApi.exportUrl(filters)" />
        <el-button v-if="!reviewing" type="primary" @click="router.push({ name: 'purchase-new' })">新建采购申请</el-button>
      </template>
    </PageToolbar>
    <el-table
      v-loading="loading"
      :data="items"
      :empty-text="reviewing ? '没有等你审批的采购申请' : '暂无采购申请'"
      row-class-name="clickable"
      @row-click="(row) => open(row.id)"
      @sort-change="sort"
    >
      <el-table-column label="编号" min-width="120">
        <template #default="{ row }">
          <RouterLink class="code" :to="detail(row.id)" @click.stop>{{ row.code }}</RouterLink>
        </template>
      </el-table-column>
      <el-table-column label="申请人" min-width="80">
        <template #default="{ row }">{{ row.owner.name }}</template>
      </el-table-column>
      <el-table-column prop="purpose" label="用途" min-width="180" show-overflow-tooltip />
      <el-table-column label="经费来源" min-width="110" show-overflow-tooltip>
        <template #default="{ row }">{{ row.fund?.code }}</template>
      </el-table-column>
      <el-table-column label="合计（元）" prop="total_amount" sortable="custom" min-width="120" align="right">
        <template #default="{ row }"><span class="amount">{{ formatMoney(row.total) }}</span></template>
      </el-table-column>
      <el-table-column label="状态" min-width="140">
        <template #default="{ row }">
          <div class="actions">
            <StatusTag :status="row.status" />
            <el-tag v-if="row.returned" class="status-tag" type="danger" disable-transitions>被退回</el-tag>
          </div>
        </template>
      </el-table-column>
      <el-table-column label="提交时间" prop="submitted_at" sortable="custom" min-width="130">
        <template #default="{ row }">{{ formatTime(row.submitted_at) }}</template>
      </el-table-column>
    </el-table>
    <el-pagination
      v-model:current-page="page"
      class="pager"
      layout="total, prev, pager, next"
      :total="count"
      :page-size="pageSize"
      hide-on-single-page
    />
  </el-card>
</template>

<style scoped>
.amount {
  font-variant-numeric: tabular-nums;
}
:deep(.clickable) {
  cursor: pointer;
}
</style>

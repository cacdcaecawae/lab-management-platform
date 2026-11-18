<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { purchasesApi } from '@/api/procurement'
import { usePagedList } from '@/composables/usePagedList'
import { useAuthStore } from '@/stores/auth'
import { PURCHASE_STATUSES, STATUS, formatMoney, formatTime } from '@/utils/format'
import StatusTag from '@/components/StatusTag.vue'

const auth = useAuthStore()
const route = useRoute()
const router = useRouter()
// Two menu items share this page: 采购申请 (all I can see) and 我的审批 (waiting for my review).
// The view is not re-created between them, so follow the route.
const reviewing = computed(() => route.name === 'purchase-reviews')
const filters = reactive({ status: '', search: '', mine: '' as 1 | '', todo: (reviewing.value ? 1 : '') as 1 | '' })
const keyword = ref('')
const { items, count, page, pageSize, loading } = usePagedList(purchasesApi.list, filters)

watch(reviewing, (r) => Object.assign(filters, { todo: r ? 1 : '', status: '', mine: '' }))

// from=reviews: the detail page's back button returns to 我的审批
const detail = (id: number) => ({ name: 'purchase-detail', params: { id }, query: reviewing.value ? { from: 'reviews' } : {} })
const open = (id: number) => router.push(detail(id))
</script>

<template>
  <el-card class="card">
    <div class="page-toolbar">
      <el-input v-model="keyword" placeholder="搜索用途、品名、申请人" clearable @change="filters.search = keyword" />
      <el-select v-if="!reviewing" v-model="filters.status" placeholder="全部状态" clearable aria-label="状态">
        <el-option v-for="s in PURCHASE_STATUSES" :key="s" :label="STATUS[s].label" :value="s" />
      </el-select>
      <el-checkbox v-if="!reviewing && auth.isSupervisor" v-model="filters.mine" :true-value="1" false-value="">只看我的</el-checkbox>
      <span class="grow" />
      <el-button v-if="!reviewing" type="primary" @click="router.push({ name: 'purchase-new' })">新建采购申请</el-button>
    </div>
    <el-table
      v-loading="loading"
      :data="items"
      :empty-text="reviewing ? '没有等你审批的采购申请' : '还没有采购申请'"
      row-class-name="clickable"
      @row-click="(row) => open(row.id)"
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
      <el-table-column label="合计（元）" min-width="110" align="right">
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
      <el-table-column label="提交时间" min-width="130">
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

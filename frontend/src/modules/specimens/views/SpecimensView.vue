<script setup lang="ts">
import { reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { specimensApi } from '../api'
import type { Specimen } from '@/api/types'
import { usePagedList } from '@/composables/usePagedList'
import { useAuthStore } from '@/stores/auth'
import { SPECIMEN_KIND_LABELS, SPECIMEN_STATUSES, STATUS } from '@/utils/format'
import StatusTag from '@/components/StatusTag.vue'
import SpecimenFormDialog from '../components/SpecimenFormDialog.vue'
import PageToolbar from '@/components/PageToolbar.vue'

const auth = useAuthStore()
const router = useRouter()
const route = useRoute()
const queryFlag = (value: unknown): 1 | '' => value === '1' ? 1 : ''
const routeFilters = () => ({
  on_loan: queryFlag(route.query.on_loan),
  mine: queryFlag(route.query.mine),
  overdue: queryFlag(route.query.overdue),
})
const filters = reactive({
  search: '',
  kind: '',
  status: '',
  ...routeFilters(),
})
watch(() => route.query, () => Object.assign(filters, routeFilters()))
const keyword = ref('')
const { items, count, page, pageSize, loading } = usePagedList(specimensApi.list, filters)
const creating = ref(false)
const selected = ref<number[]>([])
const selectLabels = (rows: Specimen[]) => { selected.value = rows.map((row) => row.id) }
const printSelected = () => router.push({ name: 'labels', query: { type: 'specimen', ids: selected.value.join(',') } })

const onCreated = (s: Specimen) => router.push({ name: 'specimen-detail', params: { id: s.id } })
</script>

<template>
  <el-card class="card">
    <PageToolbar>
      <el-input v-model="keyword" placeholder="搜索编号、名称、材料、位置" clearable @change="filters.search = keyword" />
      <el-select v-model="filters.kind" aria-label="类别" placeholder="全部类别" clearable>
        <el-option v-for="(label, k) in SPECIMEN_KIND_LABELS" :key="k" :label="label" :value="k" />
      </el-select>
      <el-select v-model="filters.status" aria-label="状态" placeholder="全部状态" clearable>
        <el-option v-for="s in SPECIMEN_STATUSES" :key="s" :label="STATUS[s].label" :value="s" />
      </el-select>
      <el-checkbox v-model="filters.on_loan" :true-value="1" false-value="">只看借出的</el-checkbox>
      <el-checkbox v-model="filters.mine" :true-value="1" false-value="">我借的</el-checkbox>
      <el-checkbox v-model="filters.overdue" :true-value="1" false-value="">逾期未还</el-checkbox>
      <template #actions>
        <el-button v-if="auth.isManager" :disabled="loading || !selected.length" @click="printSelected">打印标签</el-button>
        <el-button v-if="auth.isManager" type="primary" @click="creating = true">新建试件</el-button>
      </template>
    </PageToolbar>
    <el-table v-loading="loading" :data="items" @selection-change="selectLabels">
      <el-table-column v-if="auth.isManager" type="selection" width="44" />
      <el-table-column label="编号" min-width="110">
        <template #default="{ row }">
          <RouterLink class="code" :to="{ name: 'specimen-detail', params: { id: row.id } }">{{ row.code }}</RouterLink>
        </template>
      </el-table-column>
      <el-table-column prop="name" label="名称" min-width="150" />
      <el-table-column label="类别" min-width="90">
        <template #default="{ row }">{{ SPECIMEN_KIND_LABELS[row.kind] }}</template>
      </el-table-column>
      <el-table-column prop="material" label="材料" min-width="90" />
      <el-table-column prop="location" label="存放位置" min-width="100" />
      <el-table-column label="状态" min-width="170">
        <template #default="{ row }">
          <div class="actions">
            <StatusTag :status="row.status" />
            <el-tag v-if="row.current_loan" class="status-tag" type="warning" disable-transitions>
              {{ row.current_loan.borrower.name }} 借用中
            </el-tag>
          </div>
        </template>
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
  <SpecimenFormDialog v-model="creating" @saved="onCreated" />
</template>

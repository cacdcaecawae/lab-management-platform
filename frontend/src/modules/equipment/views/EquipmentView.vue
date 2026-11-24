<script setup lang="ts">
import { reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { equipmentApi } from '../api'
import type { Equipment } from '@/api/types'
import { usePagedList } from '@/composables/usePagedList'
import { useLiveSearch } from '@/composables/useLiveSearch'
import { useOptions } from '@/composables/useOptions'
import { useSuggestions } from '@/api/suggestions'
import { membersApi } from '@/modules/members/api'
import { useAuthStore } from '@/stores/auth'
import { EQUIPMENT_STATUSES, STATUS } from '@/utils/format'
import StatusTag from '@/components/StatusTag.vue'
import EquipmentFormDialog from '../components/EquipmentFormDialog.vue'
import PageToolbar from '@/components/PageToolbar.vue'
import { Histogram, Printer } from '@element-plus/icons-vue'
import IconButton from '@/components/IconButton.vue'

const auth = useAuthStore()
const route = useRoute()
const router = useRouter()
// ?status= comes from the workbench tile (待检查的设备)
const routeFilters = () => ({
  status: String(route.query.status ?? ''),
  calibration_within: route.query.calibration_within === '30' ? 30 as number | '' : '',
})
const filters = reactive({
  search: '',
  category: '',
  location: '',
  custodian: '' as number | '',
  idle: '' as 1 | '',
  ...routeFilters(),
})
watch(() => route.query, () => Object.assign(filters, routeFilters()))
const keyword = useLiveSearch(filters)
const categories = useSuggestions('equipment.category')
const locations = useSuggestions('equipment.location')
const members = useOptions(() => membersApi.list({ page_size: 100 }))
const { items, count, page, pageSize, loading, sort } = usePagedList(equipmentApi.list, filters)
// ?new=1&purchase=&code=&name= : 登记为设备 on an arrived purchase request opens the form filled in
const preset = route.query.new === '1' && Number(route.query.purchase)
  ? { name: String(route.query.name ?? ''), purchase: { id: Number(route.query.purchase), code: String(route.query.code ?? '') } }
  : undefined
const creating = ref(!!preset)
if (preset) void router.replace({ query: {} }) // taken: reloading the list must not open the form again
const selected = ref<number[]>([])
const selectLabels = (rows: Equipment[]) => { selected.value = rows.map((row) => row.id) }
const printSelected = () => router.push({ name: 'labels', query: { type: 'equipment', ids: selected.value.join(',') } })

const onCreated = (e: Equipment) => router.push({ name: 'equipment-detail', params: { id: e.id } })
</script>

<template>
  <el-card class="card">
    <PageToolbar>
      <el-input v-model="keyword" placeholder="搜索编号、名称、型号、位置" clearable @change="filters.search = keyword" />
      <el-select v-model="filters.status" aria-label="状态" placeholder="全部状态" clearable>
        <el-option v-for="s in EQUIPMENT_STATUSES" :key="s" :label="STATUS[s].label" :value="s" />
      </el-select>
      <el-select v-model="filters.category" aria-label="类别" placeholder="全部类别" clearable filterable remote :remote-method="categories.search">
        <el-option v-for="v in categories.values.value" :key="v" :label="v" :value="v" />
      </el-select>
      <el-select v-model="filters.location" aria-label="存放位置" placeholder="全部位置" clearable filterable remote :remote-method="locations.search">
        <el-option v-for="v in locations.values.value" :key="v" :label="v" :value="v" />
      </el-select>
      <el-select v-model="filters.custodian" aria-label="保管人" placeholder="全部保管人" clearable filterable>
        <el-option v-for="m in members" :key="m.id" :label="m.name" :value="m.id" />
      </el-select>
      <el-checkbox v-model="filters.calibration_within" :true-value="30" false-value="">校准到期（含已过期）</el-checkbox>
      <el-checkbox v-model="filters.idle" :true-value="1" false-value="">现在空闲</el-checkbox>
      <template #actions>
        <IconButton v-if="auth.isSupervisor" :icon="Histogram" label="使用统计" @click="router.push({ name: 'equipment-stats' })" />
        <IconButton v-if="auth.isManager" :icon="Printer" label="打印标签" :disabled="loading || !selected.length" @click="printSelected" />
        <el-button v-if="auth.isManager" type="primary" @click="creating = true">新建设备</el-button>
      </template>
    </PageToolbar>
    <el-table empty-text="暂无设备" v-loading="loading" :data="items" @selection-change="selectLabels" @sort-change="sort">
      <el-table-column v-if="auth.isManager" type="selection" width="44" />
      <el-table-column label="编号" prop="code" sortable="custom" min-width="100">
        <template #default="{ row }">
          <RouterLink class="code" :to="{ name: 'equipment-detail', params: { id: row.id } }">{{ row.code }}</RouterLink>
        </template>
      </el-table-column>
      <el-table-column prop="name" label="名称" min-width="140" />
      <el-table-column prop="model" label="型号" min-width="110" />
      <el-table-column prop="category" label="类别" min-width="90" />
      <el-table-column prop="location" label="存放位置" min-width="110" />
      <el-table-column label="保管人" min-width="80">
        <template #default="{ row }">{{ row.custodian?.name }}</template>
      </el-table-column>
      <el-table-column label="状态" min-width="130">
        <template #default="{ row }">
          <div class="actions">
            <StatusTag :status="row.status" />
            <el-tag v-if="row.in_use" class="status-tag" type="primary" disable-transitions>使用中</el-tag>
          </div>
        </template>
      </el-table-column>
      <el-table-column prop="calibration_due" label="下次校准" sortable="custom" min-width="110" />
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
  <EquipmentFormDialog v-model="creating" :initial="preset" @saved="onCreated" />
</template>

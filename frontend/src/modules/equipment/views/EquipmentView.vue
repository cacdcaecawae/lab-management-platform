<script setup lang="ts">
import { reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { equipmentApi } from '../api'
import type { Equipment } from '@/api/types'
import { usePagedList } from '@/composables/usePagedList'
import { useAuthStore } from '@/stores/auth'
import { EQUIPMENT_STATUSES, STATUS } from '@/utils/format'
import StatusTag from '@/components/StatusTag.vue'
import EquipmentFormDialog from '../components/EquipmentFormDialog.vue'

const auth = useAuthStore()
const route = useRoute()
const router = useRouter()
// ?status= comes from the workbench tile (待检查的设备)
const filters = reactive({ status: String(route.query.status ?? ''), search: '' })
const keyword = ref('')
const { items, count, page, pageSize, loading } = usePagedList(equipmentApi.list, filters)
const creating = ref(false)
const selected = ref<number[]>([])
const selectLabels = (rows: Equipment[]) => { selected.value = rows.map((row) => row.id) }
const printSelected = () => router.push({ name: 'labels', query: { type: 'equipment', ids: selected.value.join(',') } })

const onCreated = (e: Equipment) => router.push({ name: 'equipment-detail', params: { id: e.id } })
</script>

<template>
  <el-card class="card">
    <div class="page-toolbar">
      <el-input v-model="keyword" placeholder="搜索编号、名称、型号、位置" clearable @change="filters.search = keyword" />
      <el-select v-model="filters.status" aria-label="状态" placeholder="全部状态" clearable>
        <el-option v-for="s in EQUIPMENT_STATUSES" :key="s" :label="STATUS[s].label" :value="s" />
      </el-select>
      <span class="grow" />
      <el-button @click="router.push({ name: 'bookings' })">预约日历</el-button>
      <el-button v-if="auth.isManager" :disabled="loading || !selected.length" @click="printSelected">打印标签</el-button>
      <el-button v-if="auth.isManager" type="primary" @click="creating = true">新增设备</el-button>
    </div>
    <el-table v-loading="loading" :data="items" @selection-change="selectLabels">
      <el-table-column v-if="auth.isManager" type="selection" width="44" />
      <el-table-column label="编号" min-width="100">
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
      <el-table-column prop="calibration_due" label="下次校准" min-width="100" />
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
  <EquipmentFormDialog v-model="creating" @saved="onCreated" />
</template>

<script setup lang="ts">
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { projectsApi } from '@/modules/projects/api'
import type { Project } from '@/api/types'
import { usePagedList } from '@/composables/usePagedList'
import { useAuthStore } from '@/stores/auth'
import { formatTime } from '@/utils/format'
import StatusTag from '@/components/StatusTag.vue'
import ProjectFormDialog from '@/modules/projects/components/ProjectFormDialog.vue'
import PageToolbar from '@/components/PageToolbar.vue'

const auth = useAuthStore()
const router = useRouter()
const filters = reactive({ status: '', search: '', mine: '' as number | '' })
const keyword = ref('')
const { items, count, page, pageSize, loading } = usePagedList(projectsApi.list, filters)
const creating = ref(false)

const onCreated = (p: Project) => router.push({ name: 'project-detail', params: { id: p.id } })
</script>

<template>
  <el-card class="card">
    <PageToolbar>
      <el-input v-model="keyword" placeholder="搜索项目名称" clearable @change="filters.search = keyword" />
      <el-select v-model="filters.status" aria-label="状态" placeholder="全部状态" clearable>
        <el-option label="进行中" value="active" />
        <el-option label="已结束" value="closed" />
      </el-select>
      <el-checkbox v-model="filters.mine" :true-value="1" false-value="">只看我的</el-checkbox>
      <template #actions>
        <el-button v-if="auth.isSupervisor" type="primary" @click="creating = true">新建项目</el-button>
      </template>
    </PageToolbar>
    <el-table v-loading="loading" :data="items">
      <el-table-column label="项目名称" min-width="160">
        <template #default="{ row }">
          <RouterLink :to="{ name: 'project-detail', params: { id: row.id } }">{{ row.name }}</RouterLink>
        </template>
      </el-table-column>
      <el-table-column label="负责人" min-width="90">
        <template #default="{ row }">{{ row.leader.name }}</template>
      </el-table-column>
      <el-table-column label="成员" min-width="160">
        <template #default="{ row }">{{ row.members.map((m: { name: string }) => m.name).join('、') }}</template>
      </el-table-column>
      <el-table-column prop="stage" label="当前阶段" min-width="110" />
      <el-table-column label="状态" min-width="90">
        <template #default="{ row }"><StatusTag :status="row.status" /></template>
      </el-table-column>
      <el-table-column label="最新进展" min-width="220" show-overflow-tooltip>
        <template #default="{ row }">
          <span v-if="row.latest_log">{{ row.latest_log.date }} {{ row.latest_log.content }}</span>
        </template>
      </el-table-column>
      <el-table-column label="更新时间" min-width="140">
        <template #default="{ row }">{{ formatTime(row.updated_at) }}</template>
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
  <ProjectFormDialog v-model="creating" @saved="onCreated" />
</template>

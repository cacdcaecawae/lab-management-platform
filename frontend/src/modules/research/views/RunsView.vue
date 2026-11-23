<script setup lang="ts">
import { reactive, ref } from 'vue'
import { runsApi } from '@/modules/research/api'
import { projectsApi } from '@/modules/projects/api'
import { membersApi } from '@/modules/members/api'
import { useOptions } from '@/composables/useOptions'
import { usePagedList } from '@/composables/usePagedList'
import { useAuthStore } from '@/stores/auth'
import { formatTime } from '@/utils/format'
import StatusTag from '@/components/StatusTag.vue'
import PageToolbar from '@/components/PageToolbar.vue'

const auth = useAuthStore()
const projects = useOptions(() => projectsApi.list({ page_size: 100 }))
const members = auth.isSupervisor ? useOptions(() => membersApi.list({ page_size: 100 })) : ref([])
const filters = reactive({ project: '' as number | '', owner: '' as number | '', status: '', search: '' })
const keyword = ref('')
const { items, count, page, pageSize, loading } = usePagedList(runsApi.list, filters)
</script>

<template>
  <el-card class="card">
    <PageToolbar>
      <el-input v-model="keyword" placeholder="搜索名称" clearable @change="filters.search = keyword" />
      <el-select v-model="filters.project" aria-label="项目" placeholder="全部项目" clearable filterable>
        <el-option v-for="p in projects" :key="p.id" :label="p.name" :value="p.id" />
      </el-select>
      <el-select v-if="auth.isSupervisor" v-model="filters.owner" aria-label="提交人" placeholder="全部成员" clearable filterable>
        <el-option v-for="m in members" :key="m.id" :label="m.name" :value="m.id" />
      </el-select>
      <el-select v-model="filters.status" aria-label="状态" placeholder="全部状态" clearable>
        <el-option label="草稿" value="draft" />
        <el-option label="已提交" value="submitted" />
      </el-select>
      <template #actions>
        <el-button type="primary" @click="$router.push({ name: 'run-new' })">新建处理记录</el-button>
      </template>
    </PageToolbar>
    <el-table empty-text="暂无数据处理记录" v-loading="loading" :data="items">
      <el-table-column label="编号" min-width="130">
        <template #default="{ row }">
          <RouterLink class="code" :to="{ name: 'run-edit', params: { id: row.id } }">{{ row.code }}</RouterLink>
        </template>
      </el-table-column>
      <el-table-column prop="title" label="任务名称" min-width="180" />
      <el-table-column label="项目" min-width="140">
        <template #default="{ row }">{{ row.project.name }}</template>
      </el-table-column>
      <el-table-column label="提交人" min-width="90">
        <template #default="{ row }">{{ row.owner.name }}</template>
      </el-table-column>
      <el-table-column prop="method_version" label="方法版本" min-width="100" />
      <el-table-column label="状态" min-width="90">
        <template #default="{ row }"><StatusTag :status="row.status" /></template>
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
</template>

<script setup lang="ts">
import { inject, reactive, ref } from 'vue'
import { routeLocationKey } from 'vue-router'
import { experimentsApi } from '@/modules/research/api'
import { projectsApi } from '@/modules/projects/api'
import { membersApi } from '@/modules/members/api'
import { useOptions } from '@/composables/useOptions'
import { usePagedList } from '@/composables/usePagedList'
import { useLiveSearch } from '@/composables/useLiveSearch'
import { useAuthStore } from '@/stores/auth'
import { formatTime } from '@/utils/format'
import StatusTag from '@/components/StatusTag.vue'
import PageToolbar from '@/components/PageToolbar.vue'

const auth = useAuthStore()
const projects = useOptions(() => projectsApi.list({ page_size: 100 }))
const members = auth.isAdvisor ? useOptions(() => membersApi.list({ page_size: 100 })) : ref([])
// ?status= and ?owner= come from the workbench (实验 / 处理记录未提交), ?project= from a project's 资产.
// Injected: the page also mounts alone in tests.
const query = inject(routeLocationKey, undefined)?.query ?? {}
const filters = reactive({
  project: (Number(query.project) || '') as number | '',
  owner: (Number(query.owner) || '') as number | '',
  status: query.status === 'draft' || query.status === 'submitted' ? query.status : '',
  search: '',
})
const keyword = useLiveSearch(filters)
const { items, count, page, pageSize, loading, sort } = usePagedList(experimentsApi.list, filters)
</script>

<template>
  <el-card class="card">
    <PageToolbar>
      <el-input v-model="keyword" placeholder="搜索名称" clearable @change="filters.search = keyword" />
      <el-select v-model="filters.project" aria-label="项目" placeholder="全部项目" clearable filterable>
        <el-option v-for="p in projects" :key="p.id" :label="p.name" :value="p.id" />
      </el-select>
      <el-select v-if="auth.isAdvisor" v-model="filters.owner" aria-label="操作人" placeholder="全部成员" clearable filterable>
        <el-option v-for="m in members" :key="m.id" :label="m.name" :value="m.id" />
      </el-select>
      <el-select v-model="filters.status" aria-label="状态" placeholder="全部状态" clearable>
        <el-option label="草稿" value="draft" />
        <el-option label="已提交" value="submitted" />
      </el-select>
      <template #actions>
        <el-button type="primary" @click="$router.push({ name: 'experiment-new' })">新建实验记录</el-button>
      </template>
    </PageToolbar>
    <el-table @sort-change="sort" empty-text="暂无实验记录" v-loading="loading" :data="items">
      <el-table-column label="编号" min-width="130">
        <template #default="{ row }">
          <RouterLink class="code" :to="{ name: 'experiment-edit', params: { id: row.id } }">{{ row.code }}</RouterLink>
        </template>
      </el-table-column>
      <el-table-column prop="title" label="实验名称" min-width="180" />
      <el-table-column label="项目" min-width="140">
        <template #default="{ row }">{{ row.project.name }}</template>
      </el-table-column>
      <el-table-column label="操作人" min-width="90">
        <template #default="{ row }">{{ row.owner.name }}</template>
      </el-table-column>
      <el-table-column prop="date" label="实验日期" sortable="custom" min-width="110" />
      <el-table-column label="状态" min-width="90">
        <template #default="{ row }"><StatusTag :status="row.status" /></template>
      </el-table-column>
      <el-table-column label="更新时间" prop="updated_at" sortable="custom" min-width="140">
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

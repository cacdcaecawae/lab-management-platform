<script setup lang="ts">
import { reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { projectsApi } from '@/modules/projects/api'
import { membersApi } from '@/modules/members/api'
import type { Project } from '@/api/types'
import { useOptions } from '@/composables/useOptions'
import { usePagedList } from '@/composables/usePagedList'
import { useLiveSearch } from '@/composables/useLiveSearch'
import { useAuthStore } from '@/stores/auth'
import { formatTime } from '@/utils/format'
import { closeTab } from '@/layouts/nav'
import StatusTag from '@/components/StatusTag.vue'
import ProjectFormDialog from '@/modules/projects/components/ProjectFormDialog.vue'
import PageToolbar from '@/components/PageToolbar.vue'

const auth = useAuthStore()
const route = useRoute()
const router = useRouter()
// ?overdue=1 comes from the workbench (组里有 N 个任务已逾期)
const fromWorkbench = route.query.overdue === '1'
const filters = reactive({
  status: '', search: '', mine: '' as number | '', leader: '' as number | '', overdue: (fromWorkbench ? 1 : '') as 1 | '',
})
const keyword = useLiveSearch(filters)
const members = useOptions(() => membersApi.list({ page_size: 100 }))
const { items, count, page, pageSize, loading } = usePagedList(projectsApi.list, filters)
const creating = ref(false)
// Only one project with overdue tasks: the workbench link opens its task board straight away.
if (fromWorkbench) {
  const stop = watch(loading, (busy) => {
    if (busy) return
    stop()
    if (count.value !== 1) return
    closeTab(route.path) // its tab holds ?overdue=1: switching back to it would jump here again
    void router.replace({ name: 'project-detail', params: { id: items.value[0].id }, query: { tab: 'tasks' } })
  })
}

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
      <el-select v-model="filters.leader" aria-label="负责人" placeholder="全部负责人" clearable filterable>
        <el-option v-for="m in members" :key="m.id" :label="m.name" :value="m.id" />
      </el-select>
      <el-checkbox v-model="filters.mine" :true-value="1" false-value="">只看我的</el-checkbox>
      <el-checkbox v-model="filters.overdue" :true-value="1" false-value="">有逾期任务</el-checkbox>
      <template #actions>
        <el-button v-if="auth.isSupervisor" type="primary" @click="creating = true">新建项目</el-button>
      </template>
    </PageToolbar>
    <el-table empty-text="暂无项目" v-loading="loading" :data="items">
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
      <el-table-column label="状态" min-width="150">
        <template #default="{ row }">
          <div class="actions">
            <StatusTag :status="row.status" />
            <el-tag v-if="row.overdue_tasks" class="status-tag" type="danger" disable-transitions>{{ row.overdue_tasks }} 个任务逾期</el-tag>
          </div>
        </template>
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

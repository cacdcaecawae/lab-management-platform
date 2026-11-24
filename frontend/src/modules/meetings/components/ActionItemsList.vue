<script setup lang="ts">
import { reactive } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { ApiError } from '@/api/client'
import { meetingsApi } from '@/modules/meetings/api'
import { membersApi } from '@/modules/members/api'
import type { MyActionItem } from '@/api/types'
import { useOptions } from '@/composables/useOptions'
import { usePagedList } from '@/composables/usePagedList'
import { useAuthStore } from '@/stores/auth'
import { toDateStr } from '@/utils/format'
import { showError } from '@/utils/errors'
import PageToolbar from '@/components/PageToolbar.vue'

// Every meeting's action items in one list, the most urgent first. Ticking one here is the same as on its meeting.
const auth = useAuthStore()
// ?owner= comes from the workbench (my action items)
const filters = reactive({ open: 1 as 1 | '', overdue: '' as 1 | '', owner: (Number(useRoute().query.owner) || '') as number | '' })
const { items, count, page, pageSize, loading } = usePagedList(meetingsApi.actions, filters)
const members = useOptions(() => membersApi.list({ page_size: 100 }))
const today = toDateStr(new Date())
const late = (a: MyActionItem) => !a.done_at && !!a.due_date && a.due_date < today
const canToggle = (a: MyActionItem) => !a.carried_to && (a.owner.id === auth.user?.id || auth.isManager)

async function toggle(a: MyActionItem, done: boolean) {
  try {
    Object.assign(a, await meetingsApi.setDone(a.id, done))
  } catch (e) {
    if (e instanceof ApiError && e.status === 403) ElMessage.error('只有负责人和管理员可以修改完成状态')
    else showError(e)
  }
}
</script>

<template>
  <PageToolbar>
    <el-select v-model="filters.owner" placeholder="全部负责人" aria-label="负责人" clearable filterable>
      <el-option v-for="m in members" :key="m.id" :label="m.name" :value="m.id" />
    </el-select>
    <el-checkbox v-model="filters.open" :true-value="1" false-value="">只看未完成</el-checkbox>
    <el-checkbox v-model="filters.overdue" :true-value="1" false-value="">已逾期</el-checkbox>
  </PageToolbar>
  <el-table v-loading="loading" :data="items" empty-text="暂无行动项">
    <el-table-column prop="content" label="事项" min-width="220" />
    <el-table-column label="负责人" min-width="90">
      <template #default="{ row }">{{ row.owner.name }}</template>
    </el-table-column>
    <el-table-column label="截止" min-width="130">
      <template #default="{ row }">
        <span :class="{ overdue: late(row as MyActionItem) }">{{ row.due_date ?? '' }}{{ late(row as MyActionItem) ? '，已逾期' : '' }}</span>
      </template>
    </el-table-column>
    <el-table-column label="组会" min-width="140">
      <template #default="{ row }">
        <RouterLink :to="{ name: 'meeting-detail', params: { id: row.meeting.id } }">{{ row.meeting.date }} {{ row.meeting.title }}</RouterLink>
      </template>
    </el-table-column>
    <el-table-column label="完成" min-width="120">
      <template #default="{ row }">
        <RouterLink v-if="row.carried_to" :to="{ name: 'meeting-detail', params: { id: row.carried_to.id } }">已转入 {{ row.carried_to.date }} 组会</RouterLink>
        <el-checkbox
          v-else
          :model-value="!!row.done_at"
          :disabled="!canToggle(row as MyActionItem)"
          :aria-label="`完成：${row.content}`"
          @change="(v) => toggle(row as MyActionItem, !!v)"
        />
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
</template>

<style scoped>
.overdue {
  color: var(--el-color-danger);
}
</style>

<script setup lang="ts">
import { reactive, ref, watch } from 'vue'
import { reportsApi } from '@/modules/reports/api'
import type { UserBrief } from '@/api/types'
import { usePagedList } from '@/composables/usePagedList'
import { useAuthStore } from '@/stores/auth'
import { STATUS, formatTime, mondayOf, notMonday } from '@/utils/format'
import { showError } from '@/utils/errors'
import StatusTag from '@/components/StatusTag.vue'
import PageToolbar from '@/components/PageToolbar.vue'

const auth = useAuthStore()
// Supervisors: 待反馈 / 未交名单 / 全部. Students only see their own reports (the API scopes the list).
const tab = ref(auth.isSupervisor ? 'pending' : 'all')
const filters = reactive({ status: auth.isSupervisor ? 'submitted' : '', week_start: '' })
const { items, count, page, pageSize, loading } = usePagedList(reportsApi.list, filters)

const missingWeek = ref(mondayOf())
const missing = ref<UserBrief[]>([])
const missingLoading = ref(false)

async function loadMissing() {
  missingLoading.value = true
  try {
    missing.value = await reportsApi.missing(missingWeek.value)
  } catch (e) {
    showError(e)
  } finally {
    missingLoading.value = false
  }
}

watch(tab, (t) => {
  if (t === 'missing') loadMissing()
  else filters.status = t === 'pending' ? 'submitted' : ''
})
watch(missingWeek, loadMissing)
</script>

<template>
  <el-card class="card">
    <el-tabs v-if="auth.isSupervisor" v-model="tab">
      <el-tab-pane label="待反馈" name="pending" />
      <el-tab-pane label="未交名单" name="missing" />
      <el-tab-pane label="全部" name="all" />
    </el-tabs>

    <template v-if="tab === 'missing'">
      <PageToolbar>
        <span>周一日期</span>
        <el-date-picker v-model="missingWeek" type="date" value-format="YYYY-MM-DD" :disabled-date="notMonday" :clearable="false" />
      </PageToolbar>
      <div v-loading="missingLoading">
        <el-empty v-if="!missing.length" description="这一周没有未交的同学" />
        <div v-else class="actions">
          <el-tag v-for="u in missing" :key="u.id" type="danger" size="large" disable-transitions>{{ u.name }}</el-tag>
        </div>
      </div>
    </template>

    <template v-else>
      <PageToolbar>
        <el-date-picker
          v-model="filters.week_start"
          type="date"
          value-format="YYYY-MM-DD"
          :disabled-date="notMonday"
          placeholder="全部周"
        />
        <el-select v-if="tab === 'all'" v-model="filters.status" aria-label="状态" placeholder="全部状态" clearable>
          <el-option v-for="s in ['draft', 'submitted', 'needs_revision', 'reviewed']" :key="s" :label="STATUS[s].label" :value="s" />
        </el-select>
        <template #actions>
          <el-button v-if="!auth.isSupervisor" type="primary" @click="$router.push({ name: 'report-new' })">写本周周报</el-button>
        </template>
      </PageToolbar>
      <el-table v-loading="loading" :data="items">
        <el-table-column v-if="auth.isSupervisor" label="学生" min-width="90">
          <template #default="{ row }">{{ row.owner.name }}</template>
        </el-table-column>
        <el-table-column prop="week_start" label="周一日期" min-width="110" />
        <el-table-column label="状态" min-width="90">
          <template #default="{ row }"><StatusTag :status="row.status" /></template>
        </el-table-column>
        <el-table-column label="提交时间" min-width="140">
          <template #default="{ row }">{{ formatTime(row.submitted_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" min-width="80" fixed="right">
          <template #default="{ row }">
            <RouterLink :to="{ name: 'report-edit', params: { id: row.id } }">
              {{ tab === 'pending' ? '查看并反馈' : '查看' }}
            </RouterLink>
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
  </el-card>
</template>

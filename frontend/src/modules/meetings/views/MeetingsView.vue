<script setup lang="ts">
import { reactive } from 'vue'
import { meetingsApi } from '@/modules/meetings/api'
import type { Meeting } from '@/api/types'
import { usePagedList } from '@/composables/usePagedList'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()
const { items, count, page, pageSize, loading } = usePagedList(meetingsApi.list, reactive({}))

const presenters = (m: Meeting) => [...new Set(m.agenda.map((a) => a.presenter.name))].join('、')
const openActions = (m: Meeting) => m.actions.filter((a) => !a.done_at).length
</script>

<template>
  <el-card class="card">
    <div class="page-toolbar">
      <span class="grow" />
      <el-button v-if="auth.isManager" type="primary" @click="$router.push({ name: 'meeting-new' })">新建组会</el-button>
    </div>
    <el-table v-loading="loading" :data="items" empty-text="还没有组会记录">
      <el-table-column label="日期" min-width="110">
        <template #default="{ row }">
          <RouterLink :to="{ name: 'meeting-detail', params: { id: row.id } }">{{ row.date }}</RouterLink>
        </template>
      </el-table-column>
      <el-table-column prop="title" label="标题" min-width="140" />
      <el-table-column label="汇报人" min-width="200">
        <template #default="{ row }">{{ presenters(row as Meeting) }}</template>
      </el-table-column>
      <el-table-column label="行动项" min-width="120">
        <template #default="{ row }">
          <span v-if="row.actions.length">未完成 {{ openActions(row as Meeting) }} / 共 {{ row.actions.length }}</span>
        </template>
      </el-table-column>
      <el-table-column label="附件" min-width="70" align="right">
        <template #default="{ row }">{{ row.files.length || '' }}</template>
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

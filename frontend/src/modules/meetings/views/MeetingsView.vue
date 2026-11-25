<script setup lang="ts">
import { computed, reactive } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { meetingsApi } from '@/modules/meetings/api'
import type { Meeting } from '@/api/types'
import { usePagedList } from '@/composables/usePagedList'
import { useLiveSearch } from '@/composables/useLiveSearch'
import { useAuthStore } from '@/stores/auth'
import PageToolbar from '@/components/PageToolbar.vue'
import ActionItemsList from '../components/ActionItemsList.vue'

const auth = useAuthStore()
const route = useRoute()
const router = useRouter()
// 组会 / 行动项 (?tab=actions, also from the workbench)
const tab = computed({
  get: () => (route.query.tab === 'actions' ? 'actions' : 'meetings'),
  set: (t: string) => void router.replace({ query: t === 'actions' ? { tab: 'actions' } : {} }),
})
const filters = reactive({ search: '' })
const keyword = useLiveSearch(filters)
const { items, count, page, pageSize, loading } = usePagedList(meetingsApi.list, filters)

const presenters = (m: Meeting) => [...new Set(m.agenda.map((a) => a.presenter.name))].join('、')
const openActions = (m: Meeting) => m.actions.filter((a) => !a.done_at).length
</script>

<template>
  <el-card class="card">
    <el-tabs v-model="tab">
      <el-tab-pane label="组会" name="meetings" />
      <el-tab-pane label="行动项" name="actions" />
    </el-tabs>
    <ActionItemsList v-if="tab === 'actions'" />
    <template v-else>
    <PageToolbar>
      <el-input v-model="keyword" placeholder="搜索标题、纪要、汇报内容、汇报人" clearable @change="filters.search = keyword" />
      <template #actions>
        <el-button v-if="auth.isSupervisor" type="primary" @click="$router.push({ name: 'meeting-new' })">新建组会</el-button>
      </template>
    </PageToolbar>
    <el-table v-loading="loading" :data="items" empty-text="暂无组会记录">
      <el-table-column label="日期" min-width="110">
        <template #default="{ row }">
          <RouterLink :to="{ name: 'meeting-detail', params: { id: row.id } }">{{ row.date }}{{ row.time ? ` ${row.time}` : '' }}</RouterLink>
        </template>
      </el-table-column>
      <el-table-column prop="title" label="标题" min-width="140" />
      <el-table-column prop="location" label="地点 / 会议号" min-width="140" show-overflow-tooltip />
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
    </template>
  </el-card>
</template>

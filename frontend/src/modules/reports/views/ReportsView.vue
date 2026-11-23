<script setup lang="ts">
import { onBeforeUnmount, reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { Download } from '@element-plus/icons-vue'
import { reportsApi } from '@/modules/reports/api'
import { membersApi } from '@/modules/members/api'
import type { UserBrief, WeeklyReportDigest } from '@/api/types'
import { useOptions } from '@/composables/useOptions'
import { usePagedList } from '@/composables/usePagedList'
import { useAuthStore } from '@/stores/auth'
import { STATUS, formatTime, mondayOf, notMonday } from '@/utils/format'
import { showError } from '@/utils/errors'
import StatusTag from '@/components/StatusTag.vue'
import PageToolbar from '@/components/PageToolbar.vue'
import IconButton from '@/components/IconButton.vue'

const auth = useAuthStore()
const router = useRouter()

const DIGEST_SECTIONS = [
  { key: 'goals', label: '本周目标' },
  { key: 'done', label: '完成工作' },
  { key: 'findings', label: '主要发现与证据' },
  { key: 'next_plan', label: '下周计划' },
] as const

// Supervisors: 待反馈 / 本周汇总 / 未交名单 / 全部. Students only see their own reports (the API scopes the list).
const tab = ref(auth.isSupervisor ? 'pending' : 'all')
const filters = reactive({
  status: auth.isSupervisor ? 'submitted' : '',
  week_start: '',
  owner: '' as number | '',
  search: '',
})
const keyword = ref('')
const members = auth.isSupervisor ? useOptions(() => membersApi.list({ page_size: 100 })) : ref([])
const { items, count, page, pageSize, loading } = usePagedList(reportsApi.list, filters)

const missingWeek = ref(mondayOf())
const missing = ref<UserBrief[] | null>(null)
const missingLoading = ref(false)
let missingSeq = 0
let missingController: AbortController | null = null

function cancelMissing() {
  missingSeq++
  missingController?.abort()
  missingController = null
  missingLoading.value = false
}

async function loadMissing() {
  const seq = ++missingSeq
  missingController?.abort()
  const controller = new AbortController()
  missingController = controller
  missing.value = null
  missingLoading.value = true
  try {
    const data = await reportsApi.missing(missingWeek.value, controller.signal)
    if (seq !== missingSeq || controller.signal.aborted) return
    missing.value = data
  } catch (e) {
    if (seq !== missingSeq || controller.signal.aborted) return
    showError(e)
  } finally {
    if (seq === missingSeq) {
      missingController = null
      missingLoading.value = false
    }
  }
}

const digestWeek = ref(mondayOf())
const digest = ref<WeeklyReportDigest | null>(null)
const digestLoading = ref(false)
let digestSeq = 0
let digestController: AbortController | null = null

function cancelDigest() {
  digestSeq++
  digestController?.abort()
  digestController = null
  digestLoading.value = false
}

async function loadDigest() {
  const seq = ++digestSeq
  digestController?.abort()
  const controller = new AbortController()
  digestController = controller
  digest.value = null
  digestLoading.value = true
  try {
    const data = await reportsApi.digest(digestWeek.value, controller.signal)
    if (seq !== digestSeq || controller.signal.aborted) return
    digest.value = data
  } catch (e) {
    if (seq !== digestSeq || controller.signal.aborted) return
    showError(e)
  } finally {
    if (seq === digestSeq) {
      digestController = null
      digestLoading.value = false
    }
  }
}

const openingThisWeek = ref(false)
async function openThisWeek() {
  openingThisWeek.value = true
  try {
    const res = await reportsApi.list({ week_start: mondayOf(), page_size: 1 })
    if (res.results.length) {
      await router.push({ name: 'report-edit', params: { id: res.results[0].id } })
    } else {
      await router.push({ name: 'report-new' })
    }
  } catch (e) {
    showError(e)
  } finally {
    openingThisWeek.value = false
  }
}

watch(tab, (t) => {
  if (t === 'missing') {
    cancelDigest()
    void loadMissing()
  } else if (t === 'digest') {
    cancelMissing()
    void loadDigest()
  } else {
    cancelMissing()
    cancelDigest()
    filters.status = t === 'pending' ? 'submitted' : ''
  }
})
watch(missingWeek, () => {
  if (tab.value === 'missing') void loadMissing()
})
watch(digestWeek, () => {
  if (tab.value === 'digest') void loadDigest()
})
onBeforeUnmount(() => {
  cancelMissing()
  cancelDigest()
})
</script>

<template>
  <el-card class="card">
    <el-tabs v-if="auth.isSupervisor" v-model="tab">
      <el-tab-pane label="待反馈" name="pending" />
      <el-tab-pane label="本周汇总" name="digest" />
      <el-tab-pane label="未交名单" name="missing" />
      <el-tab-pane label="全部" name="all" />
    </el-tabs>

    <template v-if="tab === 'missing'">
      <PageToolbar :foldable="false">
        <span>周一日期</span>
        <el-date-picker v-model="missingWeek" type="date" value-format="YYYY-MM-DD" :disabled-date="notMonday" :clearable="false" />
      </PageToolbar>
      <div v-loading="missingLoading">
        <el-result v-if="missing === null && !missingLoading" icon="warning" title="未交名单加载失败">
          <template #extra><el-button @click="loadMissing">重试</el-button></template>
        </el-result>
        <el-empty v-else-if="missing?.length === 0" description="这一周没有未交的同学" />
        <div v-else-if="missing" class="actions">
          <el-tag v-for="u in missing" :key="u.id" type="danger" size="large" disable-transitions>{{ u.name }}</el-tag>
        </div>
      </div>
    </template>

    <template v-else-if="tab === 'digest'">
      <PageToolbar :foldable="false">
        <span>周一日期</span>
        <el-date-picker v-model="digestWeek" type="date" value-format="YYYY-MM-DD" :disabled-date="notMonday" :clearable="false" />
        <template #actions>
          <IconButton :icon="Download" label="导出汇总 Markdown" tag="a" :href="reportsApi.digestExportUrl(digestWeek)" />
        </template>
      </PageToolbar>
      <div v-loading="digestLoading" class="digest-wrap">
        <template v-if="digest">
          <div class="digest-summary">
            <span>已交 <strong>{{ digest.reports.length }}</strong> 份</span>
            <span class="muted">·</span>
            <template v-if="digest.missing.length">
              <span>未交（{{ digest.missing.length }} 人）：</span>
              <el-tag v-for="u in digest.missing" :key="u.id" type="danger" size="small" disable-transitions>{{ u.name }}</el-tag>
            </template>
            <span v-else class="muted">本周全员已交</span>
          </div>

          <el-empty v-if="!digest.reports.length" description="这一周还没有已提交的周报" />

          <article v-for="r in digest.reports" :key="r.id" class="digest-item">
            <header class="digest-head">
              <div class="actions">
                <RouterLink class="digest-owner" :to="{ name: 'report-edit', params: { id: r.id } }">{{ r.owner.name }}</RouterLink>
                <StatusTag :status="r.status" />
                <span v-if="r.submitted_at" class="muted">{{ formatTime(r.submitted_at) }}</span>
              </div>
              <RouterLink :to="{ name: 'report-edit', params: { id: r.id } }">
                {{ r.status === 'submitted' ? '去反馈' : '查看详情' }}
              </RouterLink>
            </header>
            <template v-for="s in DIGEST_SECTIONS" :key="s.key">
              <section v-if="r[s.key]" class="digest-section">
                <div class="digest-label">{{ s.label }}</div>
                <pre class="pre">{{ r[s.key] }}</pre>
              </section>
            </template>
            <div v-if="!r.goals && !r.done && !r.findings && !r.next_plan" class="muted">（暂未填写正文）</div>
            <div v-if="r.experiments.length || r.datasets.length || r.runs.length" class="digest-links">
              <RouterLink v-for="x in r.experiments" :key="`e${x.id}`" :to="{ name: 'experiment-edit', params: { id: x.id } }">
                实验 {{ x.code }} {{ x.title }}
              </RouterLink>
              <RouterLink
                v-for="x in r.datasets"
                :key="`d${x.id}`"
                :to="{ name: 'dataset-detail', params: { id: x.id }, query: x.version ? { version: x.version } : {} }"
              >
                数据 {{ x.code }} {{ x.name }}
              </RouterLink>
              <RouterLink v-for="x in r.runs" :key="`r${x.id}`" :to="{ name: 'run-edit', params: { id: x.id } }">
                处理 {{ x.code }} {{ x.title }}
              </RouterLink>
            </div>
          </article>
        </template>
      </div>
    </template>

    <template v-else>
      <PageToolbar>
        <el-input v-model="keyword" placeholder="搜索周报内容或姓名" clearable @change="filters.search = keyword" />
        <el-select v-if="auth.isSupervisor" v-model="filters.owner" aria-label="成员" placeholder="全部成员" clearable filterable>
          <el-option v-for="m in members" :key="m.id" :label="m.name" :value="m.id" />
        </el-select>
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
          <el-button v-if="!auth.isSupervisor" type="primary" :loading="openingThisWeek" @click="openThisWeek">写本周周报</el-button>
        </template>
      </PageToolbar>
      <el-table empty-text="暂无周报" v-loading="loading" :data="items">
        <el-table-column v-if="auth.isSupervisor" label="学生" min-width="90">
          <template #default="{ row }">
            <RouterLink :to="{ name: 'report-edit', params: { id: row.id } }">{{ row.owner.name }}</RouterLink>
          </template>
        </el-table-column>
        <el-table-column label="周一日期" min-width="110">
          <template #default="{ row }">
            <RouterLink v-if="!auth.isSupervisor" :to="{ name: 'report-edit', params: { id: row.id } }">{{ row.week_start }}</RouterLink>
            <template v-else>{{ row.week_start }}</template>
          </template>
        </el-table-column>
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

<style scoped>
.digest-wrap {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.digest-summary {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  padding: 10px 14px;
  border-radius: var(--lab-radius);
  background: var(--lab-bg-subtle);
  border: 1px solid var(--lab-border);
}
.digest-item {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 16px;
  border-radius: var(--lab-radius);
  border: 1px solid var(--lab-border);
  background: var(--lab-bg-card);
}
.digest-head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding-bottom: 8px;
  border-bottom: 1px solid var(--lab-border);
}
.digest-owner {
  font-weight: 600;
}
.digest-section {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.digest-label {
  color: var(--lab-text-3);
  font-weight: 600;
}
.digest-links {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 14px;
  padding-top: 6px;
  border-top: 1px solid var(--lab-border);
}
</style>

<script setup lang="ts">
import { replaceSavedEditor } from '@/router/saved-editor'
import { computed, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { ApiError } from '@/api/client'
import { datasetsApi } from '@/modules/datasets/api'
import { experimentsApi, runsApi } from '@/modules/research/api'
import { reportsApi } from '@/modules/reports/api'
import type { DatasetBrief, ExperimentBrief, ReportWrite, RunBrief, Verdict, WeeklyReport } from '@/api/types'
import { useOptions } from '@/composables/useOptions'
import { useAuthStore } from '@/stores/auth'
import { formatTime, mergeById, mondayOf, notMonday } from '@/utils/format'
import { errorMessage, showError, useFieldErrors } from '@/utils/errors'
import StatusTag from '@/components/StatusTag.vue'
import HistoryDrawer from '@/components/HistoryDrawer.vue'
import PageHeader from '@/components/PageHeader.vue'
import { useUnsavedGuard } from '@/composables/useUnsavedGuard'
import { Clock } from '@element-plus/icons-vue'
import IconButton from '@/components/IconButton.vue'

const auth = useAuthStore()
const route = useRoute()
const router = useRouter()

const SECTIONS = [
  { key: 'goals', label: '本周目标' },
  { key: 'done', label: '完成工作' },
  { key: 'findings', label: '主要发现与证据' },
  { key: 'next_plan', label: '下周计划' },
] as const

const record = ref<WeeklyReport | null>(null)
const loadError = ref('') // replaces the page; 404 reads 记录不存在或无权查看
const loading = ref(false)
const saving = ref(false)
const carrying = ref(false)
const historyOpen = ref(false)
const nextPendingId = ref<number | null>(null)

const weekFromQuery = typeof route.query.week_start === 'string' ? route.query.week_start : ''
const form = reactive<ReportWrite>({
  week_start: weekFromQuery || mondayOf(),
  goals: '',
  done: '',
  findings: '',
  next_plan: '',
  experiment_ids: [],
  dataset_ids: [],
  run_ids: [],
})
const errors = useFieldErrors(Object.keys(form))

// No record yet only means "new" on the -new route; a failed load must not turn into a create form.
const isNew = computed(() => !route.params.id)
const isOwner = computed(() => (record.value ? record.value.owner.id === auth.user?.id : isNew.value))
const editable = computed(() => (record.value ? isOwner.value && ['draft', 'needs_revision'].includes(record.value.status) : isNew.value))
const canDelete = computed(() => record.value?.status === 'draft' && isOwner.value)
// Ask before leaving with unsaved changes (fill() takes the snapshot).
const { markSaved } = useUnsavedGuard(form, () => editable.value)
const canFeedback = computed(() => record.value?.status === 'submitted' && auth.isSupervisor && !isOwner.value)
const feedback = computed(() => [...(record.value?.feedback ?? [])].sort((a, b) => b.created_at.localeCompare(a.created_at)))
const revisionNote = computed(() => feedback.value.find((f) => f.verdict === 'needs_revision'))

// Links are limited to the report owner's own records; whoever can edit is the owner.
const mine = { owner: auth.user?.id, page_size: 100 }
const experiments = useOptions(() => experimentsApi.list(mine))
const datasets = useOptions(() => datasetsApi.list(mine))
const runs = useOptions(() => runsApi.list(mine))
const experimentOptions = computed(() => mergeById<ExperimentBrief>(experiments.value, record.value?.experiments ?? []))
const datasetOptions = computed(() => mergeById<DatasetBrief>(datasets.value, record.value?.datasets ?? []))
const runOptions = computed(() => mergeById<RunBrief>(runs.value, record.value?.runs ?? []))

function fill(r: WeeklyReport) {
  record.value = r
  Object.assign(form, {
    week_start: r.week_start,
    goals: r.goals,
    done: r.done,
    findings: r.findings,
    next_plan: r.next_plan,
    experiment_ids: r.experiments.map((x) => x.id),
    dataset_ids: r.datasets.map((x) => x.id),
    run_ids: r.runs.map((x) => x.id),
  })
  markSaved()
}

let loadSeq = 0
async function load(id: number) {
  const mySeq = ++loadSeq
  loading.value = true
  try {
    const data = await reportsApi.get(id)
    if (mySeq !== loadSeq) return
    fill(data)
  } catch (e) {
    if (mySeq === loadSeq) loadError.value = errorMessage(e)
  } finally {
    if (mySeq === loadSeq) loading.value = false
  }
}

async function carryLastPlan() {
  carrying.value = true
  try {
    const page = await reportsApi.list({ owner: auth.user?.id, page_size: 10 })
    const prev = page.results.find((r) => r.week_start < form.week_start)
    if (!prev) {
      ElMessage.info('没有找到更早的周报')
      return
    }
    const detail = await reportsApi.get(prev.id)
    if (!detail.next_plan.trim()) {
      ElMessage.info(`上周（${detail.week_start}）周报没有填写下周计划`)
      return
    }
    if (form.goals.trim()) {
      try {
        await ElMessageBox.confirm('当前「本周目标」已有内容，是否用上周的下周计划覆盖？', '带入上周计划', {
          confirmButtonText: '覆盖',
          cancelButtonText: '取消',
        })
      } catch {
        return
      }
    }
    form.goals = detail.next_plan
    ElMessage.success(`已带入 ${detail.week_start} 周报的下周计划`)
  } catch (e) {
    showError(e)
  } finally {
    carrying.value = false
  }
}

async function save(): Promise<WeeklyReport | null> {
  saving.value = true
  try {
    const source = router.currentRoute?.value
    const r = record.value ? await reportsApi.update(record.value.id, form) : await reportsApi.create(form)
    errors.clear()
    // Replace right away so a second click updates this report instead of creating another one.
    if (!record.value && source) void replaceSavedEditor(router, source, { name: 'report-edit', params: { id: r.id } })
    fill(r)
    return r
  } catch (e) {
    if (e instanceof ApiError && e.body.code === 'conflict') {
      errors.clear()
      ElMessage.error(`${form.week_start} 这一周的周报已经存在，请在周报列表中打开它继续编辑`)
    } else errors.handle(e)
    return null
  } finally {
    saving.value = false
  }
}

async function saveDraft() {
  if (await save()) ElMessage.success('已保存')
}

async function submit() {
  const r = await save()
  if (!r) return
  saving.value = true
  try {
    fill(await reportsApi.submit(r.id))
    ElMessage.success('周报已提交')
  } catch (e) {
    errors.handle(e)
  } finally {
    saving.value = false
  }
}

async function removeDraft() {
  if (!record.value) return
  try {
    await ElMessageBox.confirm('确定删除这份草稿？删除后无法恢复。', '删除草稿', {
      type: 'warning',
      confirmButtonText: '删除',
      cancelButtonText: '取消',
    })
  } catch {
    return
  }
  saving.value = true
  try {
    await reportsApi.remove(record.value.id)
    markSaved()
    ElMessage.success('草稿已删除')
    await router.push({ name: 'reports' })
  } catch (e) {
    showError(e)
  } finally {
    saving.value = false
  }
}

// ---- supervisor feedback ----
const fb = reactive({ verdict: 'reviewed' as Verdict, content: '' })
const fbErrors = useFieldErrors(['verdict', 'content'])
const sending = ref(false)

async function sendFeedback() {
  if (fb.verdict === 'needs_revision' && !fb.content.trim()) {
    ElMessage.error('选择"需补充"时请写明需要补充的内容')
    return
  }
  sending.value = true
  try {
    const currentId = record.value!.id
    fill(await reportsApi.feedback(currentId, fb))
    fb.content = ''
    fbErrors.clear()
    ElMessage.success('反馈已提交')
    try {
      const pending = await reportsApi.list({ status: 'submitted', page_size: 5 })
      const next = pending.results.find((r) => r.id !== currentId && r.owner.id !== auth.user?.id)
      nextPendingId.value = next ? next.id : null
    } catch {
      nextPendingId.value = null
    }
  } catch (e) {
    fbErrors.handle(e)
  } finally {
    sending.value = false
  }
}

function goNextPending() {
  if (!nextPendingId.value) return
  void router.push({ name: 'report-edit', params: { id: nextPendingId.value } })
}

watch(
  () => route.params.id,
  (idParam) => {
    if (!idParam) return
    const num = Number(idParam)
    if (record.value?.id !== num) {
      loadError.value = ''
      nextPendingId.value = null
      load(num)
    }
  },
)

if (route.params.id) load(Number(route.params.id))
</script>

<template>
  <el-result v-if="loadError" icon="warning" :title="loadError">
    <template #extra><el-button @click="router.push({ name: 'reports' })">返回周报</el-button></template>
  </el-result>
  <template v-else>
    <el-card v-loading="loading" class="card">
      <template #header>
        <PageHeader :back="{ name: 'reports' }" :title="record ? `${record.owner.name} · ${record.week_start} 这一周` : '写周报'">
          <template v-if="record" #tags><StatusTag :status="record.status" /></template>
          <IconButton v-if="record" :icon="Clock" label="修改历史" @click="historyOpen = true" />
          <el-button v-if="nextPendingId" type="primary" @click="goNextPending">下一份待反馈</el-button>
          <template v-if="editable">
            <el-button v-if="isNew" :loading="carrying" @click="carryLastPlan">带入上周计划</el-button>
            <el-button v-if="canDelete" type="danger" plain :loading="saving" @click="removeDraft">删除草稿</el-button>
            <el-button :loading="saving" @click="saveDraft">保存草稿</el-button>
            <el-button type="primary" :loading="saving" @click="submit">
              {{ record?.status === 'needs_revision' ? '修改后重新提交' : '提交' }}
            </el-button>
          </template>
        </PageHeader>
      </template>

      <el-alert
        v-if="record?.status === 'needs_revision'"
        type="error"
        show-icon
        :closable="false"
        class="notice"
        :title="`导师要求补充${revisionNote ? `（${revisionNote.author.name}）` : ''}`"
      >
        <pre v-if="revisionNote" class="pre">{{ revisionNote.content }}</pre>
      </el-alert>
      <el-alert v-for="msg in errors.others.value" :key="msg" :title="msg" type="error" :closable="false" class="notice" />

      <el-form v-if="editable" class="form-page" label-position="top">
        <el-form-item label="周一日期" :error="errors.fe('week_start')" required>
          <el-date-picker
            v-model="form.week_start"
            type="date"
            value-format="YYYY-MM-DD"
            :disabled-date="notMonday"
            :clearable="false"
          />
        </el-form-item>
        <el-form-item v-for="s in SECTIONS" :key="s.key" :label="s.label" :error="errors.fe(s.key)">
          <el-input v-model="form[s.key]" type="textarea" :autosize="{ minRows: 4 }" />
        </el-form-item>
        <el-form-item label="关联实验记录" :error="errors.fe('experiment_ids')">
          <el-select v-model="form.experiment_ids" multiple filterable placeholder="选择自己的实验记录">
            <el-option v-for="x in experimentOptions" :key="x.id" :label="`${x.code} ${x.title}`" :value="x.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="关联数据集" :error="errors.fe('dataset_ids')">
          <el-select v-model="form.dataset_ids" multiple filterable placeholder="选择自己的数据集">
            <el-option v-for="x in datasetOptions" :key="x.id" :label="`${x.code} ${x.name}`" :value="x.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="关联数据处理记录" :error="errors.fe('run_ids')">
          <el-select v-model="form.run_ids" multiple filterable placeholder="选择自己的数据处理记录">
            <el-option v-for="x in runOptions" :key="x.id" :label="`${x.code} ${x.title}`" :value="x.id" />
          </el-select>
        </el-form-item>
      </el-form>

      <template v-else-if="record">
        <div class="meta">提交时间：{{ formatTime(record.submitted_at) || '未提交' }}</div>
        <section v-for="s in SECTIONS" :key="s.key" class="section">
          <h4>{{ s.label }}</h4>
          <pre class="pre">{{ record[s.key] || '（未填写）' }}</pre>
        </section>
        <section class="section">
          <h4>关联记录</h4>
          <div class="links">
            <RouterLink v-for="x in record.experiments" :key="`e${x.id}`" :to="{ name: 'experiment-edit', params: { id: x.id } }">
              实验 {{ x.code }} {{ x.title }}
            </RouterLink>
            <RouterLink
              v-for="x in record.datasets"
              :key="`d${x.id}`"
              :to="{ name: 'dataset-detail', params: { id: x.id }, query: x.version ? { version: x.version } : {} }"
            >
              数据 {{ x.code }} {{ x.name }}{{ x.version ? ` @ ${x.version.slice(0, 12)}` : '' }}{{ x.changed ? '（提交后有新增）' : '' }}
            </RouterLink>
            <RouterLink v-for="x in record.runs" :key="`r${x.id}`" :to="{ name: 'run-edit', params: { id: x.id } }">
              处理 {{ x.code }} {{ x.title }}
            </RouterLink>
            <span v-if="!record.experiments.length && !record.datasets.length && !record.runs.length" class="muted">无</span>
          </div>
        </section>
      </template>
    </el-card>

    <el-card v-if="canFeedback" class="card" header="填写反馈">
      <el-form label-position="top" @submit.prevent="sendFeedback">
        <el-form-item label="结论" :error="fbErrors.fe('verdict')">
          <el-radio-group v-model="fb.verdict">
            <el-radio value="reviewed">已阅</el-radio>
            <el-radio value="needs_revision">需补充</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="反馈内容" :error="fbErrors.fe('content')" :required="fb.verdict === 'needs_revision'">
          <el-input
            v-model="fb.content"
            type="textarea"
            :autosize="{ minRows: 3 }"
            :placeholder="fb.verdict === 'needs_revision' ? '写明需要补充什么（必填）' : '可选'"
          />
        </el-form-item>
        <el-alert v-for="msg in fbErrors.others.value" :key="msg" :title="msg" type="error" :closable="false" class="notice" />
        <el-button type="primary" native-type="submit" :loading="sending">提交反馈</el-button>
      </el-form>
    </el-card>

    <el-card v-if="feedback.length" class="card" header="导师反馈">
      <el-timeline>
        <el-timeline-item v-for="f in feedback" :key="f.id" :timestamp="formatTime(f.created_at)" placement="top">
          <div class="actions">
            <strong>{{ f.author.name }}</strong>
            <StatusTag :status="f.verdict" />
          </div>
          <pre v-if="f.content" class="pre content">{{ f.content }}</pre>
        </el-timeline-item>
      </el-timeline>
    </el-card>

    <HistoryDrawer v-if="record" v-model="historyOpen" :load="() => reportsApi.history(record!.id)" />
  </template>
</template>

<style scoped>
.notice {
  margin-bottom: 16px;
}
.meta {
  color: var(--el-text-color-secondary);
}
.section h4 {
  margin: 20px 0 8px;
}
.links {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.content {
  margin-top: 6px;
}
</style>

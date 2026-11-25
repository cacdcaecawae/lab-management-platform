<script setup lang="ts">
import { replaceSavedEditor } from '@/router/saved-editor'
import { computed, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { datasetsApi } from '@/modules/datasets/api'
import { projectsApi } from '@/modules/projects/api'
import { experimentsApi, runsApi } from '@/modules/research/api'
import type { CitedExperiment, Experiment, ProcessingRun, ProjectBrief, RunWrite } from '@/api/types'
import { useOptions } from '@/composables/useOptions'
import { useRemoteOptions } from '@/composables/useRemoteOptions'
import { useAuthStore } from '@/stores/auth'
import { formatTime, mergeById } from '@/utils/format'
import { errorMessage, showError, useFieldErrors } from '@/utils/errors'
import StatusTag from '@/components/StatusTag.vue'
import ParamsEditor from '@/modules/research/components/ParamsEditor.vue'
import HistoryDrawer from '@/components/HistoryDrawer.vue'
import PinnedDatasets from '@/components/PinnedDatasets.vue'
import PageHeader from '@/components/PageHeader.vue'
import DataFilesPanel, { type DataFilesApi } from '@/components/DataFilesPanel.vue'
import { closeTab } from '@/layouts/nav'
import { useUnsavedGuard } from '@/composables/useUnsavedGuard'
import { Clock, CopyDocument } from '@element-plus/icons-vue'
import IconButton from '@/components/IconButton.vue'

const auth = useAuthStore()
const route = useRoute()
const router = useRouter()

const record = ref<ProcessingRun | null>(null)
const copiedFrom = ref<ProcessingRun | null>(null)
const loadError = ref('') // replaces the page; 404 reads 记录不存在或无权查看
const loading = ref(false)
const saving = ref(false)
const historyOpen = ref(false)
const paramsEditor = ref<InstanceType<typeof ParamsEditor>>()

const form = reactive<RunWrite>({
  project_id: null,
  title: '',
  experiment_ids: [],
  script_dataset_id: undefined,
  script_repo: '',
  script_commit: '',
  script_path: '',
  method: '',
  method_version: '',
  params: {},
  environment: '',
  conclusion: '',
})
// experiments / script / results: what a submit finds missing
const errors = useFieldErrors([...Object.keys(form), 'experiments', 'script', 'results'])
const experimentsError = computed(() => errors.fe('experiment_ids') || errors.fe('experiments'))
const scriptError = computed(() => errors.fe('script') || errors.fe('script_repo') || errors.fe('script_commit'))

// No record yet only means "new" on the -new route; a failed load must not turn into a create form.
const isNew = computed(() => !route.params.id)
const isOwner = computed(() => (record.value ? record.value.owner.id === auth.user?.id : isNew.value))
const editable = computed(() => isOwner.value && (!record.value || record.value.status === 'draft'))
const canDelete = computed(() => !!record.value && editable.value)
// Ask before leaving with unsaved changes (fill() takes the snapshot).
// a parameter value without a name is not in form.params yet
const { markSaved } = useUnsavedGuard(form, () => editable.value, () => paramsEditor.value?.validate() === false)
const canReturn = computed(() => record.value?.status === 'submitted' && auth.isAdvisor)
const readonlyHint = computed(() => {
  const r = record.value
  if (!r || editable.value) return ''
  if (r.status === 'draft') return `${r.owner.name} 的草稿，只有本人可以编辑。`
  return `${r.owner.name} 于 ${formatTime(r.submitted_at)} 提交，记录已锁定${isOwner.value ? '；如需修改，请联系导师退回。' : '。'}`
})

const projects = useOptions(() => projectsApi.list({ page_size: 100 }))
const projectOptions = computed(() => mergeById<ProjectBrief>(projects.value, [record.value?.project, copiedFrom.value?.project]))
// One's own records and the ones shared through a project; the server checks again.
const experiments = useRemoteOptions<Experiment | CitedExperiment>((search) => experimentsApi.list({ search, page_size: 20 }))
const experimentOptions = computed(() =>
  experiments.options([
    ...form.experiment_ids, ...(record.value?.experiments ?? []),
    ...(copiedFrom.value?.experiments ?? []).filter((e) => form.experiment_ids.includes(e.id)), // what the copy took
  ]),
)
const label = (e: Experiment | CitedExperiment) =>
  `${e.code} ${e.title}${e.owner.id === auth.user?.id ? '' : `（${e.owner.name}）`}`

function fill(r: ProcessingRun) {
  record.value = r
  copiedFrom.value = null
  Object.assign(form, {
    project_id: r.project?.id ?? null,
    title: r.title,
    experiment_ids: r.experiments.map((e) => e.id),
    script_dataset_id: undefined,
    script_repo: r.script_repo,
    script_commit: r.script_commit,
    script_path: r.script_path,
    method: r.method,
    method_version: r.method_version,
    params: { ...r.params },
    environment: r.environment,
    conclusion: r.conclusion,
  })
  markSaved()
}

// A copy of one's own run cites the same data and shares its uploaded scripts; the results are its own.
function prefillCopy(src: ProcessingRun) {
  record.value = null
  copiedFrom.value = src
  const own = src.owner.id === auth.user?.id
  Object.assign(form, {
    project_id: src.project?.id ?? null,
    title: `${src.title}（复制）`,
    experiment_ids: own ? src.experiments.map((e) => e.id) : [],
    script_dataset_id: own ? src.script_dataset?.id : undefined,
    script_repo: src.script_repo,
    script_commit: src.script_commit,
    script_path: src.script_path,
    method: src.method,
    method_version: src.method_version,
    params: { ...src.params },
    environment: src.environment,
    conclusion: '',
  })
  markSaved()
}

async function load(id: number) {
  loading.value = true
  try {
    fill(await runsApi.get(id))
  } catch (e) {
    loadError.value = errorMessage(e)
  } finally {
    loading.value = false
  }
}

async function loadCopy(copyId: number) {
  loading.value = true
  try {
    const src = await runsApi.get(copyId)
    prefillCopy(src)
    ElMessage.info(`已从 ${src.code} 带入配置，请上传结果文件后保存`)
  } catch (e) {
    showError(e)
  } finally {
    loading.value = false
  }
}

function copyAsDraft() {
  if (!record.value) return
  void router.push({ name: 'run-new', query: { copy: String(record.value.id) } })
}

async function save(): Promise<ProcessingRun | null> {
  if (paramsEditor.value && !paramsEditor.value.validate()) {
    ElMessage.error('处理参数有误，请检查')
    return null
  }
  saving.value = true
  try {
    const source = router.currentRoute?.value
    const r = record.value ? await runsApi.update(record.value.id, form) : await runsApi.create(form)
    errors.clear()
    // Replace right away so a second click updates this draft instead of creating another one.
    if (!record.value && source) void replaceSavedEditor(router, source, { name: 'run-edit', params: { id: r.id } })
    fill(r)
    return r
  } catch (e) {
    errors.handle(e)
    return null
  } finally {
    saving.value = false
  }
}

async function saveDraft() {
  if (await save()) ElMessage.success('草稿已保存')
}

async function submit() {
  const r = await save()
  if (!r) return
  saving.value = true
  try {
    fill(await runsApi.submit(r.id))
    ElMessage.success('已提交，记录已锁定')
  } catch (e) {
    errors.handle(e) // reproducibility check: errors name what is missing
  } finally {
    saving.value = false
  }
}

async function removeDraft() {
  if (!record.value) return
  try {
    await ElMessageBox.confirm('确定删除这条记录？它的脚本和结果文件会一起删除，无法恢复。', '删除记录', {
      type: 'warning',
      confirmButtonText: '删除',
      cancelButtonText: '取消',
    })
  } catch {
    return
  }
  saving.value = true
  try {
    await runsApi.remove(record.value.id)
    markSaved()
    closeTab(route.path)
    ElMessage.success('记录已删除')
    await router.push({ name: 'runs' })
  } catch (e) {
    showError(e)
  } finally {
    saving.value = false
  }
}

async function returnToDraft() {
  let reason = ''
  try {
    ;({ value: reason } = await ElMessageBox.prompt('退回后记录回到草稿状态，由本人修改后重新提交。', '退回数据处理记录', {
      inputType: 'textarea',
      inputPlaceholder: '退回原因（必填）',
      inputValidator: (v) => !!v?.trim() || '请填写退回原因',
    }))
  } catch {
    return
  }
  try {
    fill(await runsApi.returnToDraft(record.value!.id, reason.trim()))
    ElMessage.success('已退回')
  } catch (e) {
    showError(e)
  }
}

// ---- script and result files: a record not saved yet is saved first ----
const filesApi: DataFilesApi = {
  files: datasetsApi.files,
  upload: (id, file, onProgress, path) => datasetsApi.uploadFile(id, file, onProgress, path),
  remove: datasetsApi.removeFile,
  zipUrl: (id) => datasetsApi.downloadZipUrl(id),
}
const prepareScripts = async () => (await save())?.script_dataset?.id ?? null
const prepareResults = async () => (await save())?.output_dataset?.id ?? null

watch(
  () => [route.params.id, route.query.copy] as const,
  ([idParam, copyParam]) => {
    if (idParam) {
      const num = Number(idParam)
      if (record.value?.id !== num) {
        loadError.value = ''
        load(num)
      }
    } else if (typeof copyParam === 'string' && Number(copyParam) > 0) {
      loadError.value = ''
      loadCopy(Number(copyParam))
    }
  },
)

if (route.params.id) load(Number(route.params.id))
else if (typeof route.query.copy === 'string' && Number(route.query.copy) > 0) loadCopy(Number(route.query.copy))
</script>

<template>
  <el-result v-if="loadError" icon="warning" :title="loadError">
    <template #extra><el-button @click="router.push({ name: 'runs' })">返回数据处理</el-button></template>
  </el-result>
  <el-card v-else v-loading="loading" class="card">
    <template #header>
      <PageHeader :back="{ name: 'runs' }">
        <template #title><template v-if="record"><span class="code">{{ record.code }}</span> {{ record.title }}</template><template v-else-if="isNew">新建数据处理</template></template>
        <template v-if="record" #tags><StatusTag :status="record.status" /></template>
        <IconButton v-if="record" :icon="CopyDocument" label="复制为新草稿" @click="copyAsDraft" />
        <IconButton v-if="record" :icon="Clock" label="修改历史" @click="historyOpen = true" />
        <el-button v-if="canReturn" type="warning" @click="returnToDraft">退回</el-button>
        <template v-if="editable">
          <el-button v-if="canDelete" type="danger" plain :loading="saving" @click="removeDraft">删除记录</el-button>
          <el-button :loading="saving" @click="saveDraft">保存草稿</el-button>
          <el-button type="primary" :loading="saving" @click="submit">提交</el-button>
        </template>
      </PageHeader>
    </template>
    <el-alert v-if="readonlyHint" :title="readonlyHint" type="info" :closable="false" class="notice" />
    <el-alert v-for="msg in errors.others.value" :key="msg" :title="msg" type="error" :closable="false" class="notice" />
    <div v-if="record || isNew" class="form-page">
      <el-form :disabled="!editable" label-position="top">
        <div class="form-grid">
          <el-form-item class="span-2" label="项目" :error="errors.fe('project_id')">
            <el-select v-model="form.project_id" filterable clearable placeholder="选填；关联项目并提交后，项目成员可以查看">
              <el-option v-for="p in projectOptions" :key="p.id" :label="p.name" :value="p.id" />
            </el-select>
          </el-form-item>
          <el-form-item class="span-2" label="任务名称" :error="errors.fe('title')" required>
            <el-input v-model="form.title" />
          </el-form-item>
        </div>
        <el-form-item label="引用的原始数据" :error="experimentsError" required>
          <el-select
            v-if="editable"
            v-model="form.experiment_ids"
            multiple
            filterable
            remote
            :remote-method="experiments.search"
            :loading="experiments.loading.value"
            placeholder="选择实验与原始数据，可搜编号、名称；也能选项目里队友已提交的"
          >
            <el-option v-for="e in experimentOptions" :key="e.id" :label="label(e)" :value="e.id" />
          </el-select>
          <div v-else class="cited">
            <div v-for="e in record?.experiments ?? []" :key="e.id" class="actions">
              <RouterLink :to="{ name: 'experiment-edit', params: { id: e.id } }"><span class="code">{{ e.code }}</span> {{ e.title }}</RouterLink>
              <span v-if="e.owner.id !== auth.user?.id" class="muted">{{ e.owner.name }}</span>
              <span v-if="e.version" class="mono muted">@ {{ e.version.slice(0, 12) }}</span>
              <el-tag v-if="e.changed" size="small" type="warning" disable-transitions>提交后有新增</el-tag>
            </div>
            <span v-if="!record?.experiments.length" class="muted">无</span>
          </div>
        </el-form-item>
      </el-form>
      <template v-if="record?.inputs.length">
        <div class="section-title">早期引用的数据集</div>
        <PinnedDatasets v-if="record.status === 'submitted'" :datasets="record.inputs" />
        <div v-else class="actions">
          <RouterLink v-for="d in record.inputs" :key="d.id" :to="{ name: 'dataset-detail', params: { id: d.id } }">
            <span class="code">{{ d.code }}</span> {{ d.name }}
          </RouterLink>
        </div>
      </template>

      <div class="section-title">处理算法</div>
      <div v-if="scriptError" class="field-error">{{ scriptError }}</div>
      <DataFilesPanel
        title="脚本文件"
        :dataset-id="record?.script_dataset?.id ?? null"
        :api="filesApi"
        :editable="isOwner"
        :version="record?.script_dataset?.version ?? null"
        :prepare="prepareScripts"
      />
      <el-form :disabled="!editable" label-position="top" class="after-files">
        <el-form-item label="git 仓库">
          <div class="script-ref">
            <el-input v-model="form.script_repo" placeholder="仓库地址" aria-label="git 仓库地址" />
            <el-input v-model="form.script_commit" placeholder="commit" aria-label="git commit" />
            <el-input v-model="form.script_path" placeholder="入口脚本，如 src/run.py" aria-label="入口脚本" />
          </div>
        </el-form-item>
        <el-form-item label="软件/方法说明" :error="errors.fe('method')">
          <el-input v-model="form.method" type="textarea" :autosize="{ minRows: 3 }" placeholder="用 Origin、Excel 或仪器软件处理时，写下做了哪些操作" />
        </el-form-item>
        <div class="form-grid">
          <el-form-item class="span-2" label="方法版本" :error="errors.fe('method_version')">
            <el-input v-model="form.method_version" />
          </el-form-item>
          <el-form-item class="span-2" label="运行环境" :error="errors.fe('environment')">
            <el-input v-model="form.environment" placeholder="如 Python 3.11 + numpy 2.1，MATLAB R2024b" />
          </el-form-item>
        </div>
        <el-form-item label="处理参数" :error="errors.fe('params')">
          <ParamsEditor ref="paramsEditor" v-model="form.params" :disabled="!editable" />
        </el-form-item>
      </el-form>

      <div class="section-title">处理结果</div>
      <div v-if="errors.fe('results')" class="field-error">{{ errors.fe('results') }}</div>
      <DataFilesPanel
        title="结果文件"
        :dataset-id="record?.output_dataset?.id ?? null"
        :api="filesApi"
        :editable="isOwner"
        :version="record?.output_dataset?.version ?? null"
        :prepare="prepareResults"
        thumbnails
      />
      <el-form :disabled="!editable" label-position="top" class="after-files">
        <el-form-item label="结论" :error="errors.fe('conclusion')">
          <el-input v-model="form.conclusion" type="textarea" :autosize="{ minRows: 4 }" />
        </el-form-item>
      </el-form>
    </div>
  </el-card>
  <HistoryDrawer v-if="record" v-model="historyOpen" :load="() => runsApi.history(record!.id)" />
</template>

<style scoped>
.notice {
  margin-bottom: 16px;
}
.section-title {
  margin: 20px 0 8px;
  padding-top: 16px;
  border-top: 1px solid var(--lab-border);
  font-weight: 600;
  color: var(--lab-text-2);
}
.field-error {
  margin-bottom: 8px;
  color: var(--el-color-danger);
  font-size: 13px;
}
.after-files {
  margin-top: 12px;
}
.cited {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.script-ref {
  display: grid;
  grid-template-columns: 5fr 3fr 4fr;
  gap: 8px;
  width: 100%;
}
@media (max-width: 768px) {
  .script-ref {
    grid-template-columns: 1fr;
  }
}
</style>

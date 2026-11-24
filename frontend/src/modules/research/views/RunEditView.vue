<script setup lang="ts">
import { replaceSavedEditor } from '@/router/saved-editor'
import { computed, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { datasetsApi } from '@/modules/datasets/api'
import { projectsApi } from '@/modules/projects/api'
import { runsApi } from '@/modules/research/api'
import type { DatasetBrief, ProcessingRun, ProjectBrief, RunWrite } from '@/api/types'
import { useOptions } from '@/composables/useOptions'
import { useRemoteOptions } from '@/composables/useRemoteOptions'
import { useAuthStore } from '@/stores/auth'
import { KIND_LABELS, formatTime, mergeById } from '@/utils/format'
import { errorMessage, showError, useFieldErrors } from '@/utils/errors'
import StatusTag from '@/components/StatusTag.vue'
import ParamsEditor from '@/modules/research/components/ParamsEditor.vue'
import HistoryDrawer from '@/components/HistoryDrawer.vue'
import PinnedDatasets from '@/components/PinnedDatasets.vue'
import PageHeader from '@/components/PageHeader.vue'
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
  input_ids: [],
  script_dataset_id: null,
  script_repo: '',
  script_commit: '',
  script_path: '',
  method_version: '',
  params: {},
  environment: '',
  output_dataset_id: null,
  conclusion: '',
})
// The script is either a script dataset or a git repo + commit (+ entry script).
const scriptMode = ref<'dataset' | 'git'>('dataset')
// `script` catches a submit error about the script as a whole.
const errors = useFieldErrors([...Object.keys(form), 'script'])
const scriptError = computed(
  () => errors.fe('script') || errors.fe('script_dataset_id') || errors.fe('script_repo') || errors.fe('script_commit'),
)

// No record yet only means "new" on the -new route; a failed load must not turn into a create form.
const isNew = computed(() => !route.params.id)
const editable = computed(() => (record.value ? record.value.status === 'draft' && record.value.owner.id === auth.user?.id : isNew.value))
const canDelete = computed(() => !!record.value && editable.value)
// Ask before leaving with unsaved changes (fill() takes the snapshot).
// a parameter value without a name is not in form.params yet
const { markSaved } = useUnsavedGuard(form, () => editable.value, () => paramsEditor.value?.validate() === false)
const canReturn = computed(() => record.value?.status === 'submitted' && auth.isAdvisor)
const readonlyHint = computed(() => {
  const r = record.value
  if (!r || editable.value) return ''
  if (r.status === 'draft') return `${r.owner.name} 的草稿，只有本人可以编辑。`
  const self = r.owner.id === auth.user?.id
  return `${r.owner.name} 于 ${formatTime(r.submitted_at)} 提交，记录已锁定${self ? '；如需修改，请联系导师退回。' : '。'}`
})

const projects = useOptions(() => projectsApi.list({ page_size: 100 }))
// Only the record owner's datasets can be referenced; whoever can edit is the owner.
const mine = (kind?: 'script' | 'result') =>
  useRemoteOptions<DatasetBrief>((search) => datasetsApi.list({ owner: auth.user?.id, kind, search, page_size: 20 }))
const inputs = mine()
const scripts = mine('script')
const results = mine('result')
const projectOptions = computed(() => mergeById<ProjectBrief>(projects.value, [record.value?.project, copiedFrom.value?.project]))
const datasetOptions = computed(() =>
  inputs.options([...form.input_ids, ...(record.value?.inputs ?? []), ...(copiedFrom.value?.inputs ?? [])]),
)
const scriptOptions = computed(() =>
  scripts.options([form.script_dataset_id, record.value?.script_dataset, copiedFrom.value?.script_dataset]),
)
const resultOptions = computed(() => results.options([form.output_dataset_id, record.value?.output_dataset]))

function fill(r: ProcessingRun) {
  record.value = r
  copiedFrom.value = null
  Object.assign(form, {
    project_id: r.project.id,
    title: r.title,
    input_ids: r.inputs.map((d) => d.id),
    script_dataset_id: r.script_dataset?.id ?? null,
    script_repo: r.script_repo,
    script_commit: r.script_commit,
    script_path: r.script_path,
    method_version: r.method_version,
    params: { ...r.params },
    environment: r.environment,
    output_dataset_id: r.output_dataset?.id ?? null,
    conclusion: r.conclusion,
  })
  scriptMode.value = r.script_repo && !r.script_dataset ? 'git' : 'dataset'
  markSaved()
}

function prefillCopy(src: ProcessingRun) {
  record.value = null
  copiedFrom.value = src
  const own = src.owner.id === auth.user?.id
  Object.assign(form, {
    project_id: src.project.id,
    title: `${src.title}（复制）`,
    input_ids: own ? src.inputs.map((d) => d.id) : [],
    script_dataset_id: own ? (src.script_dataset?.id ?? null) : null,
    script_repo: src.script_repo,
    script_commit: src.script_commit,
    script_path: src.script_path,
    method_version: src.method_version,
    params: { ...src.params },
    environment: src.environment,
    output_dataset_id: null,
    conclusion: '',
  })
  scriptMode.value = src.script_repo && !src.script_dataset ? 'git' : 'dataset'
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
    ElMessage.info(`已从 ${src.code} 带入配置，请补充结果数据集后保存`)
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
  // Clear the option that was not chosen so only one script source is stored.
  const body: RunWrite =
    scriptMode.value === 'dataset'
      ? { ...form, script_repo: '', script_commit: '', script_path: '' }
      : { ...form, script_dataset_id: null }
  saving.value = true
  try {
    const source = router.currentRoute?.value
    const r = record.value ? await runsApi.update(record.value.id, body) : await runsApi.create(body)
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
    await runsApi.remove(record.value.id)
    markSaved()
    ElMessage.success('草稿已删除')
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
        <template #title><template v-if="record"><span class="code">{{ record.code }}</span> {{ record.title }}</template><template v-else-if="isNew">新建数据处理记录</template></template>
        <template v-if="record" #tags><StatusTag :status="record.status" /></template>
        <IconButton v-if="record" :icon="CopyDocument" label="复制为新草稿" @click="copyAsDraft" />
        <IconButton v-if="record" :icon="Clock" label="修改历史" @click="historyOpen = true" />
        <el-button v-if="canReturn" type="warning" @click="returnToDraft">退回</el-button>
        <template v-if="editable">
          <el-button v-if="canDelete" type="danger" plain :loading="saving" @click="removeDraft">删除草稿</el-button>
          <el-button :loading="saving" @click="saveDraft">保存草稿</el-button>
          <el-button type="primary" :loading="saving" @click="submit">提交</el-button>
        </template>
      </PageHeader>
    </template>
    <el-alert v-if="readonlyHint" :title="readonlyHint" type="info" :closable="false" class="notice" />
    <el-alert v-for="msg in errors.others.value" :key="msg" :title="msg" type="error" :closable="false" class="notice" />
    <el-form v-if="record || isNew" class="form-page" :disabled="!editable" label-position="top">
      <div class="form-grid">
        <el-form-item class="span-2" label="项目" :error="errors.fe('project_id')" required>
          <el-select v-model="form.project_id" filterable placeholder="选择项目">
            <el-option v-for="p in projectOptions" :key="p.id" :label="p.name" :value="p.id" />
          </el-select>
        </el-form-item>
        <el-form-item class="span-2" label="任务名称" :error="errors.fe('title')" required>
          <el-input v-model="form.title" />
        </el-form-item>
      </div>
      <el-form-item label="输入数据集（只能选择自己的数据集）" :error="errors.fe('input_ids')" required>
        <el-select v-model="form.input_ids" multiple filterable remote :remote-method="inputs.search" :loading="inputs.loading.value" placeholder="选择输入数据，可搜编号、名称">
          <el-option v-for="d in datasetOptions" :key="d.id" :label="`${d.code} ${d.name}（${KIND_LABELS[d.kind]}）`" :value="d.id" />
        </el-select>
      </el-form-item>
      <el-form-item label="脚本" :error="scriptError" required>
        <div class="script">
          <el-radio-group v-model="scriptMode">
            <el-radio value="dataset">脚本数据集</el-radio>
            <el-radio value="git">git 仓库</el-radio>
          </el-radio-group>
          <el-select
            v-if="scriptMode === 'dataset'"
            v-model="form.script_dataset_id"
            filterable
            remote
            :remote-method="scripts.search"
            :loading="scripts.loading.value"
            clearable
            placeholder="选择类型为「脚本」的数据集"
          >
            <el-option v-for="d in scriptOptions" :key="d.id" :label="`${d.code} ${d.name}`" :value="d.id" />
          </el-select>
          <div v-else class="script-ref">
            <el-input v-model="form.script_repo" placeholder="仓库地址" />
            <el-input v-model="form.script_commit" placeholder="commit" />
            <el-input v-model="form.script_path" placeholder="入口脚本，如 src/run.py" />
          </div>
        </div>
      </el-form-item>
      <div class="form-grid">
        <el-form-item class="span-2" label="方法版本" :error="errors.fe('method_version')">
          <el-input v-model="form.method_version" />
        </el-form-item>
        <el-form-item class="span-2" label="运行环境" :error="errors.fe('environment')" required>
          <el-input v-model="form.environment" placeholder="如 Python 3.11 + numpy 2.1，MATLAB R2024b" />
        </el-form-item>
      </div>
      <el-form-item label="处理参数" :error="errors.fe('params')">
        <ParamsEditor ref="paramsEditor" v-model="form.params" :disabled="!editable" />
      </el-form-item>
      <el-form-item label="结果数据集" :error="errors.fe('output_dataset_id')" required>
        <el-select v-model="form.output_dataset_id" filterable remote :remote-method="results.search" :loading="results.loading.value" clearable placeholder="选择类型为「处理结果」的数据集">
          <el-option v-for="d in resultOptions" :key="d.id" :label="`${d.code} ${d.name}`" :value="d.id" />
        </el-select>
      </el-form-item>
      <el-form-item label="结论" :error="errors.fe('conclusion')">
        <el-input v-model="form.conclusion" type="textarea" :autosize="{ minRows: 4 }" />
      </el-form-item>
    </el-form>
    <PinnedDatasets v-if="record?.status === 'submitted'" :datasets="[...record.inputs, record.script_dataset, record.output_dataset]" />
  </el-card>
  <HistoryDrawer v-if="record" v-model="historyOpen" :load="() => runsApi.history(record!.id)" />
</template>

<style scoped>
.notice {
  margin-bottom: 16px;
}
.script-ref {
  display: grid;
  grid-template-columns: 5fr 3fr 4fr;
  gap: 8px;
}
@media (max-width: 768px) {
  .script-ref {
    grid-template-columns: 1fr;
  }
}
.script {
  display: flex;
  flex-direction: column;
  gap: 8px;
  width: 100%;
}
</style>

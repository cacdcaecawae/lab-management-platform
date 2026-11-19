<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { datasetsApi } from '@/modules/datasets/api'
import { projectsApi } from '@/modules/projects/api'
import { runsApi } from '@/modules/research/api'
import type { DatasetBrief, ProcessingRun, ProjectBrief, RunWrite } from '@/api/types'
import { useOptions } from '@/composables/useOptions'
import { useAuthStore } from '@/stores/auth'
import { KIND_LABELS, formatTime, mergeById } from '@/utils/format'
import { errorMessage, showError, useFieldErrors } from '@/utils/errors'
import StatusTag from '@/components/StatusTag.vue'
import ParamsEditor from '@/modules/research/components/ParamsEditor.vue'
import HistoryDrawer from '@/components/HistoryDrawer.vue'
import PinnedDatasets from '@/components/PinnedDatasets.vue'

const auth = useAuthStore()
const route = useRoute()
const router = useRouter()

const record = ref<ProcessingRun | null>(null)
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
const isNew = !route.params.id
const editable = computed(() => (record.value ? record.value.status === 'draft' && record.value.owner.id === auth.user?.id : isNew))
const canReturn = computed(() => record.value?.status === 'submitted' && auth.isSupervisor)
const readonlyHint = computed(() => {
  const r = record.value
  if (!r || editable.value) return ''
  if (r.status === 'draft') return `${r.owner.name} 的草稿，只有本人可以编辑。`
  const self = r.owner.id === auth.user?.id
  return `${r.owner.name} 于 ${formatTime(r.submitted_at)} 提交，记录已锁定${self ? '；如需修改，请联系导师退回。' : '。'}`
})

const projects = useOptions(() => projectsApi.list({ page_size: 100 }))
// Only the record owner's datasets can be referenced; whoever can edit is the owner.
const mine = useOptions(() => datasetsApi.list({ owner: auth.user?.id, page_size: 100 }))
const projectOptions = computed(() => mergeById<ProjectBrief>(projects.value, [record.value?.project]))
const datasetOptions = computed(() =>
  mergeById<DatasetBrief>(mine.value, [...(record.value?.inputs ?? []), record.value?.script_dataset, record.value?.output_dataset]),
)
const scriptOptions = computed(() => datasetOptions.value.filter((d) => d.kind === 'script'))
const resultOptions = computed(() => datasetOptions.value.filter((d) => d.kind === 'result'))

function fill(r: ProcessingRun) {
  record.value = r
  Object.assign(form, {
    project_id: r.project.id,
    title: r.title,
    input_ids: r.inputs.map((d) => d.id),
    script_dataset_id: r.script_dataset?.id ?? null,
    script_repo: r.script_repo,
    script_commit: r.script_commit,
    script_path: r.script_path,
    method_version: r.method_version,
    params: r.params,
    environment: r.environment,
    output_dataset_id: r.output_dataset?.id ?? null,
    conclusion: r.conclusion,
  })
  scriptMode.value = r.script_repo && !r.script_dataset ? 'git' : 'dataset'
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
    const r = record.value ? await runsApi.update(record.value.id, body) : await runsApi.create(body)
    errors.clear()
    // Replace right away so a second click updates this draft instead of creating another one.
    if (!record.value) router.replace({ name: 'run-edit', params: { id: r.id } })
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

if (route.params.id) load(Number(route.params.id))
</script>

<template>
  <el-result v-if="loadError" icon="warning" :title="loadError">
    <template #extra><el-button @click="router.push({ name: 'runs' })">返回数据处理</el-button></template>
  </el-result>
  <el-card v-else v-loading="loading" class="card">
    <template #header>
      <div class="actions">
        <el-page-header :content="record ? `${record.code} ${record.title}` : '新建数据处理记录'" @back="router.push({ name: 'runs' })" />
        <StatusTag v-if="record" :status="record.status" />
        <span style="flex: 1" />
        <el-button v-if="record" @click="historyOpen = true">修改历史</el-button>
        <el-button v-if="canReturn" type="warning" @click="returnToDraft">退回</el-button>
        <template v-if="editable">
          <el-button :loading="saving" @click="saveDraft">保存草稿</el-button>
          <el-button type="primary" :loading="saving" @click="submit">提交</el-button>
        </template>
      </div>
    </template>
    <el-alert v-if="readonlyHint" :title="readonlyHint" type="info" :closable="false" class="notice" />
    <el-alert v-for="msg in errors.others.value" :key="msg" :title="msg" type="error" :closable="false" class="notice" />
    <el-form :disabled="!editable" label-position="top">
      <el-row :gutter="16">
        <el-col :xs="24" :sm="12">
          <el-form-item label="项目" :error="errors.fe('project_id')" required>
            <el-select v-model="form.project_id" filterable placeholder="选择项目">
              <el-option v-for="p in projectOptions" :key="p.id" :label="p.name" :value="p.id" />
            </el-select>
          </el-form-item>
        </el-col>
        <el-col :xs="24" :sm="12">
          <el-form-item label="任务名称" :error="errors.fe('title')" required>
            <el-input v-model="form.title" />
          </el-form-item>
        </el-col>
      </el-row>
      <el-form-item label="输入数据集（只能选择自己的数据集）" :error="errors.fe('input_ids')" required>
        <el-select v-model="form.input_ids" multiple filterable placeholder="选择输入数据">
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
            clearable
            placeholder="选择类型为「脚本」的数据集"
          >
            <el-option v-for="d in scriptOptions" :key="d.id" :label="`${d.code} ${d.name}`" :value="d.id" />
          </el-select>
          <el-row v-else :gutter="8">
            <el-col :xs="24" :sm="10"><el-input v-model="form.script_repo" placeholder="仓库地址" /></el-col>
            <el-col :xs="24" :sm="6"><el-input v-model="form.script_commit" placeholder="commit" /></el-col>
            <el-col :xs="24" :sm="8"><el-input v-model="form.script_path" placeholder="入口脚本，如 src/run.py" /></el-col>
          </el-row>
        </div>
      </el-form-item>
      <el-row :gutter="16">
        <el-col :xs="24" :sm="12">
          <el-form-item label="方法版本" :error="errors.fe('method_version')">
            <el-input v-model="form.method_version" />
          </el-form-item>
        </el-col>
        <el-col :xs="24" :sm="12">
          <el-form-item label="运行环境" :error="errors.fe('environment')" required>
            <el-input v-model="form.environment" placeholder="如 Python 3.11 + numpy 2.1，MATLAB R2024b" />
          </el-form-item>
        </el-col>
      </el-row>
      <el-form-item label="处理参数" :error="errors.fe('params')">
        <ParamsEditor ref="paramsEditor" v-model="form.params" :disabled="!editable" />
      </el-form-item>
      <el-form-item label="结果数据集" :error="errors.fe('output_dataset_id')" required>
        <el-select v-model="form.output_dataset_id" filterable clearable placeholder="选择类型为「处理结果」的数据集">
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
.script {
  display: flex;
  flex-direction: column;
  gap: 8px;
  width: 100%;
}
</style>

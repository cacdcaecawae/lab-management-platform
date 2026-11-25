<script setup lang="ts">
import { replaceSavedEditor } from '@/router/saved-editor'
import { computed, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { datasetsApi } from '@/modules/datasets/api'
import { equipmentApi } from '@/modules/equipment/api'
import { specimensApi } from '@/modules/specimens/api'
import { projectsApi } from '@/modules/projects/api'
import { experimentsApi } from '@/modules/research/api'
import type { DatasetReferences, EquipmentBrief, Experiment, ExperimentWrite, ProjectBrief, SpecimenBrief } from '@/api/types'
import { useOptions } from '@/composables/useOptions'
import { useRemoteOptions } from '@/composables/useRemoteOptions'
import { useAuthStore } from '@/stores/auth'
import { formatTime, mergeById, toDateStr } from '@/utils/format'
import { errorMessage, showError, useFieldErrors } from '@/utils/errors'
import { preparePhoto } from '@/utils/image'
import StatusTag from '@/components/StatusTag.vue'
import ParamsEditor from '@/modules/research/components/ParamsEditor.vue'
import HistoryDrawer from '@/components/HistoryDrawer.vue'
import PinnedDatasets from '@/components/PinnedDatasets.vue'
import PageHeader from '@/components/PageHeader.vue'
import AttachmentList from '@/components/AttachmentList.vue'
import DataFilesPanel, { type DataFilesApi } from '@/components/DataFilesPanel.vue'
import RecordReferences from '@/components/RecordReferences.vue'
import { closeTab } from '@/layouts/nav'
import { useUnsavedGuard } from '@/composables/useUnsavedGuard'
import { Clock, CopyDocument } from '@element-plus/icons-vue'
import IconButton from '@/components/IconButton.vue'

const auth = useAuthStore()
const route = useRoute()
const router = useRouter()

const record = ref<Experiment | null>(null)
const copiedFrom = ref<Experiment | null>(null)
const loadError = ref('') // replaces the page; 404 reads 记录不存在或无权查看
const loading = ref(false)
const saving = ref(false)
const historyOpen = ref(false)
const paramsEditor = ref<InstanceType<typeof ParamsEditor>>()
const refs = ref<DatasetReferences | null>(null)

const blank = (): ExperimentWrite => ({
  project_id: null,
  title: '',
  date: toDateStr(new Date()),
  equipment_item_id: null,
  equipment: '',
  specimen: '',
  specimen_item_ids: [],
  params: {},
  steps: '',
  anomalies: '',
})
const form = reactive<ExperimentWrite>(blank())
const errors = useFieldErrors(Object.keys(form))

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
const equipment = useOptions(() => equipmentApi.list({ page_size: 100 }))
const equipmentOptions = computed(() => mergeById<EquipmentBrief>(equipment.value, [record.value?.equipment_item, copiedFrom.value?.equipment_item]))
const specimens = useRemoteOptions<SpecimenBrief>((search) => specimensApi.list({ search, page_size: 20 }))
const specimenOptions = computed(() =>
  specimens.options([...form.specimen_item_ids, ...(record.value?.specimen_items ?? []), ...(copiedFrom.value?.specimen_items ?? [])]),
)
const projectOptions = computed(() => mergeById<ProjectBrief>(projects.value, [record.value?.project, copiedFrom.value?.project]))

function fill(r: Experiment) {
  record.value = r
  copiedFrom.value = null
  Object.assign(form, {
    project_id: r.project?.id ?? null,
    title: r.title,
    date: r.date,
    equipment_item_id: r.equipment_item?.id ?? null,
    equipment: r.equipment,
    specimen: r.specimen,
    specimen_item_ids: r.specimen_items.map((s) => s.id),
    params: { ...r.params },
    steps: r.steps,
    anomalies: r.anomalies,
  })
  markSaved()
}

// The files and photos are not copied: a copy records another acquisition.
function prefillCopy(src: Experiment) {
  record.value = null
  copiedFrom.value = src
  Object.assign(form, {
    project_id: src.project?.id ?? null,
    title: `${src.title}（复制）`,
    date: toDateStr(new Date()),
    equipment_item_id: src.equipment_item?.id ?? null,
    equipment: src.equipment,
    specimen: src.specimen,
    specimen_item_ids: src.specimen_items.map((s) => s.id),
    params: { ...src.params },
    steps: src.steps,
    anomalies: '',
  })
  markSaved()
}

// ?project= / ?equipment= / ?date= open the new page already filled in (e.g. after logging an equipment booking).
function prefillFromQuery() {
  const q = route.query
  const id = (v: unknown) => (typeof v === 'string' && Number(v) > 0 ? Number(v) : null)
  Object.assign(form, blank(), {
    project_id: id(q.project),
    equipment_item_id: id(q.equipment),
    date: typeof q.date === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(q.date) ? q.date : toDateStr(new Date()),
  })
  markSaved()
}

async function load(id: number) {
  loading.value = true
  try {
    fill(await experimentsApi.get(id))
  } catch (e) {
    loadError.value = errorMessage(e)
  } finally {
    loading.value = false
  }
}

async function loadCopy(copyId: number) {
  loading.value = true
  try {
    const src = await experimentsApi.get(copyId)
    prefillCopy(src)
    ElMessage.info(`已从 ${src.code} 带入内容，请确认后保存`)
  } catch (e) {
    showError(e)
  } finally {
    loading.value = false
  }
}

function copyAsDraft() {
  if (!record.value) return
  void router.push({ name: 'experiment-new', query: { copy: String(record.value.id) } })
}

async function save(): Promise<Experiment | null> {
  if (paramsEditor.value && !paramsEditor.value.validate()) {
    ElMessage.error('实验参数有误，请检查')
    return null
  }
  saving.value = true
  try {
    const source = router.currentRoute?.value
    const r = record.value ? await experimentsApi.update(record.value.id, form) : await experimentsApi.create(form)
    errors.clear()
    // Replace right away so a second click updates this draft instead of creating another one.
    if (!record.value && source) void replaceSavedEditor(router, source, { name: 'experiment-edit', params: { id: r.id } })
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
    fill(await experimentsApi.submit(r.id))
    ElMessage.success('已提交，记录已锁定')
  } catch (e) {
    errors.handle(e)
  } finally {
    saving.value = false
  }
}

async function removeDraft() {
  if (!record.value) return
  try {
    await ElMessageBox.confirm('确定删除这条记录？它的原始数据文件和照片会一起删除，无法恢复。', '删除记录', {
      type: 'warning',
      confirmButtonText: '删除',
      cancelButtonText: '取消',
    })
  } catch {
    return
  }
  saving.value = true
  try {
    await experimentsApi.remove(record.value.id)
    markSaved()
    closeTab(route.path)
    ElMessage.success('记录已删除')
    await router.push({ name: 'experiments' })
  } catch (e) {
    showError(e)
  } finally {
    saving.value = false
  }
}

async function returnToDraft() {
  let reason = ''
  try {
    ;({ value: reason } = await ElMessageBox.prompt('退回后记录回到草稿状态，由本人修改后重新提交。', '退回实验记录', {
      inputType: 'textarea',
      inputPlaceholder: '退回原因（必填）',
      inputValidator: (v) => !!v?.trim() || '请填写退回原因',
    }))
  } catch {
    return
  }
  try {
    fill(await experimentsApi.returnToDraft(record.value!.id, reason.trim()))
    ElMessage.success('已退回')
  } catch (e) {
    showError(e)
  }
}

// ---- photos and raw data: a record not saved yet is saved first ----
async function savedRecord() {
  const r = record.value ?? (await save())
  if (!r) throw new Error('请先填好实验名称和日期')
  return r
}

async function uploadPhoto(file: File, _kind: unknown, onProgress: (percent: number) => void) {
  const r = await savedRecord()
  const photo = await experimentsApi.uploadPhoto(r.id, await preparePhoto(file), onProgress)
  record.value?.photos.push(photo)
}

async function removePhoto(photoId: number) {
  await experimentsApi.removePhoto(photoId)
  if (record.value) record.value.photos = record.value.photos.filter((p) => p.id !== photoId)
}

const filesApi: DataFilesApi = {
  files: datasetsApi.files,
  upload: (id, file, onProgress, path) => datasetsApi.uploadFile(id, file, onProgress, path),
  remove: datasetsApi.removeFile,
  zipUrl: (id) => datasetsApi.downloadZipUrl(id),
}

async function prepareFiles() {
  return (await save())?.dataset?.id ?? null
}

function filesChanged(count: number) {
  if (record.value) record.value.file_count = count
}

// Where this record's data is cited: processing runs and weekly reports the viewer may see.
watch(
  () => record.value?.dataset?.id,
  async (datasetId) => {
    refs.value = null
    if (!datasetId) return
    try {
      const found = await datasetsApi.references(datasetId)
      if (datasetId === record.value?.dataset?.id) refs.value = found
    } catch (e) {
      showError(e)
    }
  },
)

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
    } else {
      // the same page reused for a new record
      record.value = copiedFrom.value = null
      loadError.value = ''
      prefillFromQuery()
    }
  },
)

if (route.params.id) load(Number(route.params.id))
else if (typeof route.query.copy === 'string' && Number(route.query.copy) > 0) loadCopy(Number(route.query.copy))
else prefillFromQuery()
</script>

<template>
  <el-result v-if="loadError" icon="warning" :title="loadError">
    <template #extra><el-button @click="router.push({ name: 'experiments' })">返回实验与原始数据</el-button></template>
  </el-result>
  <template v-else>
    <el-card v-loading="loading" class="card">
      <template #header>
        <PageHeader :back="{ name: 'experiments' }">
          <template #title><template v-if="record"><span class="code">{{ record.code }}</span> {{ record.title }}</template><template v-else-if="isNew">新建实验与原始数据</template></template>
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
      <template v-if="record || isNew">
        <el-form class="form-page" :disabled="!editable" label-position="top">
          <div class="form-grid">
            <el-form-item class="span-2" label="项目" :error="errors.fe('project_id')">
              <el-select v-model="form.project_id" filterable clearable placeholder="选填；关联项目并提交后，项目成员可以查看">
                <el-option v-for="p in projectOptions" :key="p.id" :label="p.name" :value="p.id" />
              </el-select>
            </el-form-item>
            <el-form-item class="span-2" label="实验名称" :error="errors.fe('title')" required>
              <el-input v-model="form.title" />
            </el-form-item>
            <el-form-item label="实验日期" :error="errors.fe('date')" required>
              <el-date-picker v-model="form.date" type="date" value-format="YYYY-MM-DD" />
            </el-form-item>
            <el-form-item label="台账设备" :error="errors.fe('equipment_item_id')">
              <el-select v-model="form.equipment_item_id" filterable clearable placeholder="从设备台账选择">
                <el-option v-for="e in equipmentOptions" :key="e.id" :label="`${e.code} ${e.name}`" :value="e.id" />
              </el-select>
            </el-form-item>
            <el-form-item class="span-2" label="设备说明" :error="errors.fe('equipment')">
              <el-input v-model="form.equipment" placeholder="台账外的设备、探头；外部导入或仿真数据可不填" />
            </el-form-item>
            <el-form-item class="span-2" label="台账试件" :error="errors.fe('specimen_item_ids')">
              <el-select v-model="form.specimen_item_ids" multiple filterable remote :remote-method="specimens.search" :loading="specimens.loading.value" placeholder="从试样与标准件中选择，可搜编号、名称">
                <el-option v-for="s in specimenOptions" :key="s.id" :label="`${s.code} ${s.name}`" :value="s.id" />
              </el-select>
            </el-form-item>
            <el-form-item class="span-2" label="试件说明" :error="errors.fe('specimen')">
              <el-input v-model="form.specimen" placeholder="台账外的试件" />
            </el-form-item>
          </div>
          <el-form-item label="实验参数" :error="errors.fe('params')">
            <ParamsEditor ref="paramsEditor" v-model="form.params" :disabled="!editable" />
          </el-form-item>
          <el-form-item label="步骤与现场记录" :error="errors.fe('steps')">
            <el-input v-model="form.steps" type="textarea" :autosize="{ minRows: 6 }" />
          </el-form-item>
          <el-form-item label="异常情况" :error="errors.fe('anomalies')">
            <el-input v-model="form.anomalies" type="textarea" :autosize="{ minRows: 3 }" />
          </el-form-item>
        </el-form>
        <div class="form-page">
          <div class="section-title">现场照片 / 现象附图</div>
          <AttachmentList
            :attachments="record?.photos ?? []"
            :upload="editable ? uploadPhoto : undefined"
            :can-delete="() => editable"
            :remove="removePhoto"
            :with-kinds="false"
            accept="image/*"
            hint="拍照或选截图，JPG、PNG、WebP"
          />
          <template v-if="record?.datasets.length">
            <div class="section-title">早期关联的数据集</div>
            <PinnedDatasets v-if="record.status === 'submitted'" :datasets="record.datasets" />
            <div v-else class="actions">
              <RouterLink v-for="d in record.datasets" :key="d.id" :to="{ name: 'dataset-detail', params: { id: d.id } }">
                <span class="code">{{ d.code }}</span> {{ d.name }}
              </RouterLink>
            </div>
          </template>
        </div>
      </template>
    </el-card>
    <el-card v-if="record || isNew" class="card" header="原始数据">
      <DataFilesPanel
        :dataset-id="record?.dataset?.id ?? null"
        :api="filesApi"
        :editable="isOwner"
        :version="record?.dataset?.version ?? null"
        :prepare="prepareFiles"
        @changed="filesChanged"
      />
      <template v-if="refs">
        <div class="section-title">被引用处</div>
        <RecordReferences :refs="refs" :self-experiment="record?.id" />
      </template>
    </el-card>
  </template>
  <HistoryDrawer v-if="record" v-model="historyOpen" :load="() => experimentsApi.history(record!.id)" />
</template>

<style scoped>
.notice {
  margin-bottom: 16px;
}
.section-title {
  margin: 16px 0 8px;
  font-weight: 600;
  color: var(--lab-text-2);
}
</style>

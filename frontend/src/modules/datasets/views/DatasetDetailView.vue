<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Download, Edit } from '@element-plus/icons-vue'
import { datasetsApi } from '@/modules/datasets/api'
import type { Dataset, DatasetReferences } from '@/api/types'
import { useAuthStore } from '@/stores/auth'
import { KIND_LABELS, formatSize, formatTime } from '@/utils/format'
import { errorMessage, showError, useFieldErrors } from '@/utils/errors'
import PageHeader from '@/components/PageHeader.vue'
import IconButton from '@/components/IconButton.vue'
import FormDialog from '@/components/FormDialog.vue'
import DataFilesPanel, { type DataFilesApi } from '@/components/DataFilesPanel.vue'
import RecordReferences from '@/components/RecordReferences.vue'
import { closeTab } from '@/layouts/nav'

// A record's files on their own page: opened from 提交时的数据版本, search results and older links. The record that
// holds them is listed under 被引用处.
const auth = useAuthStore()
const route = useRoute()
const router = useRouter()
const id = Number(route.params.id)

const dataset = ref<Dataset | null>(null)
const refs = ref<DatasetReferences>({ experiments: [], runs: [], reports: [] })
const loadError = ref('') // replaces the page; 404 reads 记录不存在或无权查看
const isOwner = computed(() => dataset.value?.owner.id === auth.user?.id)
const hasReferences = computed(
  () => refs.value.experiments.length > 0 || refs.value.runs.length > 0 || refs.value.reports.length > 0,
)
const refsFailed = ref(false) // 被引用处 unknown: not offered for deletion here
const canDelete = computed(() => isOwner.value && dataset.value?.file_count === 0 && !refsFailed.value && !hasReferences.value)
// ?version=<code>: the file list a submitted record pinned; files uploaded later are marked.
const version = computed(() => (typeof route.query.version === 'string' ? route.query.version : ''))

const filesApi: DataFilesApi = {
  files: datasetsApi.files,
  upload: (datasetId, file, onProgress, path) => datasetsApi.uploadFile(datasetId, file, onProgress, path),
  remove: datasetsApi.removeFile,
  zipUrl: (datasetId) => datasetsApi.downloadZipUrl(datasetId),
}

async function load() {
  try {
    dataset.value = await datasetsApi.get(id)
  } catch (e) {
    loadError.value = errorMessage(e)
    return
  }
  try {
    refs.value = await datasetsApi.references(id)
    refsFailed.value = false
  } catch (e) {
    refsFailed.value = true
    showError(e)
  }
}

async function reloadDataset() {
  try {
    dataset.value = await datasetsApi.get(id) // file count and version after an upload or a deletion
  } catch (e) {
    showError(e)
  }
}

// ---- edit dataset metadata ----
const editOpen = ref(false)
const editForm = reactive({ name: '', description: '' })
const editErrors = useFieldErrors(['name', 'description'])
const savingEdit = ref(false)

function openEdit() {
  if (!dataset.value) return
  editForm.name = dataset.value.name
  editForm.description = dataset.value.description
  editErrors.clear()
  editOpen.value = true
}

async function saveEdit() {
  savingEdit.value = true
  try {
    dataset.value = await datasetsApi.update(id, { name: editForm.name, description: editForm.description })
    editOpen.value = false
    ElMessage.success('已保存')
  } catch (e) {
    editErrors.handle(e)
  } finally {
    savingEdit.value = false
  }
}

// ---- delete empty unreferenced dataset ----
const deleting = ref(false)
async function removeDataset() {
  if (!dataset.value) return
  try {
    await ElMessageBox.confirm(`确定删除空数据集「${dataset.value.name}」？删除后无法恢复。`, '删除数据集', {
      type: 'warning',
      confirmButtonText: '删除',
      cancelButtonText: '取消',
    })
  } catch {
    return
  }
  deleting.value = true
  try {
    await datasetsApi.remove(id)
    closeTab(route.path)
    ElMessage.success('数据集已删除')
    await router.push({ name: 'experiments' })
  } catch (e) {
    showError(e)
  } finally {
    deleting.value = false
  }
}

load()
</script>

<template>
  <el-result v-if="loadError" icon="warning" :title="loadError">
    <template #extra><el-button @click="router.push({ name: 'experiments' })">返回实验与原始数据</el-button></template>
  </el-result>
  <template v-else-if="dataset">
    <el-card class="card">
      <template #header>
        <PageHeader :back="{ name: 'experiments' }">
          <template #title><span class="code">{{ dataset.code }}</span> {{ dataset.name }}</template>
          <IconButton
            v-if="dataset.file_count > 0"
            :icon="Download"
            :label="version ? '打包下载这一版本 ZIP' : '打包下载 ZIP'"
            tag="a"
            :href="datasetsApi.downloadZipUrl(dataset.id, version || undefined)"
          />
          <IconButton v-if="isOwner" :icon="Edit" label="编辑数据集" @click="openEdit" />
          <el-button v-if="canDelete" type="danger" plain :loading="deleting" @click="removeDataset">删除数据集</el-button>
        </PageHeader>
      </template>
      <el-descriptions :column="1" border>
        <el-descriptions-item label="类型">{{ KIND_LABELS[dataset.kind] }}</el-descriptions-item>
        <el-descriptions-item label="项目">{{ dataset.project?.name ?? '—' }}</el-descriptions-item>
        <el-descriptions-item label="创建人">{{ dataset.owner.name }}</el-descriptions-item>
        <el-descriptions-item label="文件">{{ dataset.file_count }} 个，共 {{ formatSize(dataset.total_size) }}</el-descriptions-item>
        <el-descriptions-item label="当前版本"><span class="mono">{{ dataset.version.slice(0, 12) }}</span></el-descriptions-item>
        <el-descriptions-item label="说明"><pre class="pre">{{ dataset.description }}</pre></el-descriptions-item>
        <el-descriptions-item label="创建时间">{{ formatTime(dataset.created_at) }}</el-descriptions-item>
      </el-descriptions>
    </el-card>

    <el-card class="card" header="文件">
      <DataFilesPanel
        :dataset-id="dataset.id"
        :api="filesApi"
        :editable="isOwner"
        :version="version || null"
        :zip="false"
        @changed="reloadDataset"
      />
    </el-card>

    <el-card class="card" header="被引用处">
      <RecordReferences :refs="refs" />
    </el-card>

    <FormDialog v-model="editOpen" title="编辑数据集" :loading="savingEdit" @submit="saveEdit">
      <el-form-item label="名称" :error="editErrors.fe('name')" required>
        <el-input v-model="editForm.name" />
      </el-form-item>
      <el-form-item label="说明" :error="editErrors.fe('description')">
        <el-input v-model="editForm.description" type="textarea" :autosize="{ minRows: 3 }" />
      </el-form-item>
      <el-alert v-for="msg in editErrors.others.value" :key="msg" :title="msg" type="error" :closable="false" />
    </FormDialog>
  </template>
</template>

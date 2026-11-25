<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Download, Upload } from '@element-plus/icons-vue'
import type { DataFile } from '@/api/types'
import { formatSize, formatTime } from '@/utils/format'
import { errorMessage, showError } from '@/utils/errors'
import { previewKindOf } from '@/utils/preview'
import { droppedFiles, type DroppedFile } from '@/utils/dropped'
import { useUnsavedGuard } from '@/composables/useUnsavedGuard'
import FilePreviewDialog, { type PreviewTarget } from '@/components/FilePreviewDialog.vue'
import IconButton from '@/components/IconButton.vue'

// A record's files (an experiment's raw data, a run's scripts or results): the list, uploading picked or dropped files
// and whole folders, preview, ZIP, and deleting an upload no submitted record pins yet. Pages pass the datasets API in
// (shared components do not import modules).
export interface DataFilesApi {
  files: (datasetId: number, version?: string) => Promise<DataFile[]>
  upload: (datasetId: number, file: File, onProgress: (percent: number) => void, path?: string) => Promise<unknown>
  remove: (fileId: number) => Promise<unknown>
  zipUrl: (datasetId: number) => string
}

const props = withDefaults(
  defineProps<{
    datasetId: number | null
    api: DataFilesApi
    title?: string
    editable?: boolean
    // the version a submitted record pinned: files uploaded since are marked
    version?: string | null
    thumbnails?: boolean
    zip?: boolean
    // a record not saved yet: save it first and give its dataset id (null when saving failed)
    prepare?: () => Promise<number | null>
  }>(),
  { title: '', editable: false, version: null, thumbnails: false, zip: true, prepare: undefined },
)
const emit = defineEmits<{ changed: [count: number] }>()

const files = ref<DataFile[]>([])
const pinnedIds = ref<Set<number> | null>(null)
const loading = ref(false)
const total = computed(() => files.value.reduce((sum, f) => sum + f.size, 0))

async function load() {
  const id = props.datasetId
  if (!id) {
    files.value = []
    pinnedIds.value = null
    return
  }
  loading.value = true
  try {
    const [all, pinned] = await Promise.all([props.api.files(id), props.version ? props.api.files(id, props.version) : null])
    if (id !== props.datasetId) return // another record opened meanwhile
    files.value = all
    pinnedIds.value = pinned && new Set(pinned.map((f) => f.id))
  } catch (e) {
    showError(e)
  } finally {
    loading.value = false
  }
}
watch(() => [props.datasetId, props.version], load, { immediate: true })
defineExpose({ reload: load })

// ---- upload: one request per file, one after another ----
interface Item {
  name: string
  progress: number
  status: 'waiting' | 'uploading' | 'done' | 'error'
  error: string
}
const queue = ref<Item[]>([])
const uploading = ref(false)
const current = computed(() => queue.value.find((q) => q.status === 'uploading'))
const finished = computed(() => queue.value.filter((q) => q.status === 'done' || q.status === 'error').length)
const failed = computed(() => queue.value.filter((q) => q.status === 'error'))
useUnsavedGuard({}, () => uploading.value, () => uploading.value) // leaving now would drop the files not sent yet

const picker = ref<HTMLInputElement>()
function onPick(e: Event) {
  const input = e.target as HTMLInputElement
  const picked = Array.from(input.files ?? []).map((file) => ({ file, path: '' }))
  input.value = '' // the same file can be picked again after an error
  void upload(picked)
}

const dragging = ref(false)
function onDrop(e: DragEvent) {
  dragging.value = false
  if (!props.editable || uploading.value || !e.dataTransfer) return
  void droppedFiles(e.dataTransfer).then(upload, showError)
}

async function upload(picked: DroppedFile[]) {
  if (!picked.length) return
  const id = props.datasetId ?? (await props.prepare?.()) ?? null
  if (!id) return
  queue.value = picked.map(({ file, path }) => ({ name: path || file.name, progress: 0, status: 'waiting', error: '' }))
  uploading.value = true
  let sent = 0
  for (const [i, { file, path }] of picked.entries()) {
    const item = queue.value[i]!
    item.status = 'uploading'
    try {
      await props.api.upload(id, file, (p) => (item.progress = p), path || undefined)
      item.status = 'done'
      sent++
    } catch (err) {
      item.status = 'error'
      item.error = errorMessage(err)
    }
  }
  uploading.value = false
  queue.value = failed.value // the uploaded ones are in the table now
  if (sent) ElMessage.success(`已上传 ${sent} 个文件`)
  await load()
  emit('changed', files.value.length)
}

async function remove(row: DataFile) {
  try {
    await ElMessageBox.confirm(`删除文件“${row.name}”？删除后无法恢复。`, '删除文件', {
      type: 'warning',
      confirmButtonText: '删除',
      cancelButtonText: '取消',
    })
  } catch {
    return
  }
  try {
    await props.api.remove(row.id)
    ElMessage.success('文件已删除')
  } catch (e) {
    showError(e)
  }
  await load()
  emit('changed', files.value.length)
}

const previewOpen = ref(false)
const previewTarget = ref<PreviewTarget | null>(null)
function openPreview(row: DataFile) {
  previewTarget.value = { name: row.name, url: row.download_url, previewUrl: row.preview_url, size: row.size }
  previewOpen.value = true
}
</script>

<template>
  <section
    class="data-files"
    :class="{ dropping: dragging }"
    @dragover.prevent="dragging = editable && !uploading"
    @dragleave.self="dragging = false"
    @drop.prevent="onDrop"
  >
    <div v-if="dragging" class="drop-hint">松开上传</div>
    <div class="head">
      <span v-if="title" class="title">{{ title }}</span>
      <span class="muted">{{ files.length }} 个文件<template v-if="files.length">，共 {{ formatSize(total) }}</template></span>
      <span class="grow" />
      <IconButton v-if="zip && datasetId && files.length" :icon="Download" label="打包下载 ZIP" tag="a" :href="api.zipUrl(datasetId)" />
      <template v-if="editable">
        <input ref="picker" type="file" multiple hidden @change="onPick" />
        <el-button :icon="Upload" :loading="uploading" @click="picker?.click()">上传文件</el-button>
      </template>
    </div>
    <div v-if="version" class="muted pinned">
      提交时的版本 <span class="mono">{{ version.slice(0, 12) }}</span>，标“提交后新增”的是之后上传的
    </div>
    <div v-if="current" class="progress">
      <div class="muted">正在上传 {{ finished + 1 }} / {{ queue.length }}：{{ current.name }}</div>
      <el-progress :percentage="current.progress" />
    </div>
    <el-alert v-for="q in failed" :key="q.name" type="error" :title="`${q.name} 上传失败：${q.error}`" :closable="false" class="failed" />
    <el-table v-loading="loading" :data="files" :empty-text="editable ? '暂无文件，可把文件或整个文件夹拖到这里' : '暂无文件'">
      <el-table-column label="文件名" min-width="200">
        <template #default="{ row }">
          <div class="name">
            <el-image
              v-if="thumbnails && previewKindOf(row.name) === 'image'"
              class="thumb"
              :src="`${row.preview_url}?raw=1`"
              fit="cover"
              :alt="row.name"
              @click="openPreview(row as DataFile)"
            />
            <span>{{ row.name }}</span>
            <el-tag v-if="pinnedIds && !pinnedIds.has(row.id)" class="status-tag" type="warning" disable-transitions>提交后新增</el-tag>
          </div>
        </template>
      </el-table-column>
      <el-table-column label="大小" prop="size" sortable min-width="90">
        <template #default="{ row }">{{ formatSize(row.size) }}</template>
      </el-table-column>
      <el-table-column label="SHA256" min-width="180" show-overflow-tooltip>
        <template #default="{ row }"><span class="mono">{{ row.sha256 }}</span></template>
      </el-table-column>
      <el-table-column label="上传时间" min-width="140">
        <template #default="{ row }">{{ formatTime(row.uploaded_at) }}</template>
      </el-table-column>
      <el-table-column label="操作" min-width="130" fixed="right">
        <template #default="{ row }">
          <div class="actions">
            <el-button v-if="previewKindOf(row.name)" link type="primary" @click="openPreview(row as DataFile)">预览</el-button>
            <el-link type="primary" :href="row.download_url">下载</el-link>
            <el-button v-if="editable && !row.locked" link type="danger" @click="remove(row as DataFile)">删除</el-button>
          </div>
        </template>
      </el-table-column>
    </el-table>
    <FilePreviewDialog v-model="previewOpen" :target="previewTarget" />
  </section>
</template>

<style scoped>
.data-files {
  position: relative;
}
.data-files.dropping {
  outline: 2px dashed var(--el-color-primary);
  outline-offset: 4px;
  border-radius: var(--lab-radius);
}
.drop-hint {
  position: absolute;
  inset: 0;
  z-index: 10; /* above the table's fixed 操作 column */
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(255, 255, 255, 0.8);
  color: var(--el-color-primary);
  pointer-events: none;
}
.head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}
.title {
  font-weight: 600;
  color: var(--lab-text);
}
.grow {
  flex: 1;
}
.muted {
  color: var(--lab-text-3);
  font-size: 13px;
}
.pinned,
.progress,
.failed {
  margin-bottom: 8px;
}
.name {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  overflow-wrap: anywhere;
}
.thumb {
  width: 40px;
  height: 40px;
  flex: none;
  border-radius: var(--el-border-radius-small);
  border: 1px solid var(--lab-border);
  cursor: zoom-in;
}
</style>

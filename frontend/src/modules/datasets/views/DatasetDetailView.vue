<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { datasetsApi, uploadFile } from '@/modules/datasets/api'
import type { DataFile, Dataset } from '@/api/types'
import { useAuthStore } from '@/stores/auth'
import { KIND_LABELS, formatSize, formatTime } from '@/utils/format'
import { errorMessage } from '@/utils/errors'
import { previewKindOf } from '@/utils/preview'
import PageHeader from '@/components/PageHeader.vue'
import FilePreviewDialog, { type PreviewTarget } from '@/components/FilePreviewDialog.vue'

const auth = useAuthStore()
const route = useRoute()
const router = useRouter()
const id = Number(route.params.id)

const dataset = ref<Dataset | null>(null)
const files = ref<DataFile[]>([])
const loadError = ref('') // replaces the page; 404 reads 记录不存在或无权查看
const isOwner = computed(() => dataset.value?.owner.id === auth.user?.id)
// ?version=<code>: the file list a submitted record pinned; files uploaded later are marked.
const version = typeof route.query.version === 'string' ? route.query.version : ''
const versionFileIds = ref<Set<number> | null>(null)
const previewOpen = ref(false)
const previewTarget = ref<PreviewTarget | null>(null)

function openPreview(row: DataFile) {
  previewTarget.value = { name: row.name, url: row.download_url, previewUrl: row.preview_url, size: row.size }
  previewOpen.value = true
}

async function load() {
  try {
    ;[dataset.value, files.value] = await Promise.all([datasetsApi.get(id), datasetsApi.files(id)])
    if (version) versionFileIds.value = new Set((await datasetsApi.files(id, version)).map((f) => f.id))
  } catch (e) {
    loadError.value = errorMessage(e)
  }
}

// ---- upload: one request per file, sequentially ----
interface UploadItem {
  name: string
  size: number
  progress: number
  status: 'waiting' | 'uploading' | 'done' | 'error'
  error: string
}
const queue = ref<UploadItem[]>([])
const uploading = ref(false)
const picker = ref<HTMLInputElement>()

async function onPick(e: Event) {
  const input = e.target as HTMLInputElement
  const picked = Array.from(input.files ?? [])
  input.value = '' // allow picking the same file again after an error
  if (!picked.length) return
  const start = queue.value.length
  queue.value.push(...picked.map((f) => ({ name: f.name, size: f.size, progress: 0, status: 'waiting' as const, error: '' })))
  uploading.value = true
  let ok = 0
  for (const [i, file] of picked.entries()) {
    const item = queue.value[start + i]
    item.status = 'uploading'
    try {
      await uploadFile(id, file, (p) => (item.progress = p))
      item.status = 'done'
      item.progress = 100
      ok++
    } catch (err) {
      item.status = 'error'
      item.error = errorMessage(err)
    }
  }
  uploading.value = false
  if (ok) ElMessage.success(`已上传 ${ok} 个文件`)
  load()
}

load()
</script>

<template>
  <el-result v-if="loadError" icon="warning" :title="loadError">
    <template #extra><el-button @click="router.push({ name: 'datasets' })">返回数据列表</el-button></template>
  </el-result>
  <template v-else-if="dataset">
    <el-card class="card">
      <template #header>
        <PageHeader :back="{ name: 'datasets' }">
          <template #title><span class="code">{{ dataset.code }}</span> {{ dataset.name }}</template>
        </PageHeader>
      </template>
      <el-descriptions :column="1" border>
        <el-descriptions-item label="类型">{{ KIND_LABELS[dataset.kind] }}</el-descriptions-item>
        <el-descriptions-item label="项目">{{ dataset.project.name }}</el-descriptions-item>
        <el-descriptions-item label="创建人">{{ dataset.owner.name }}</el-descriptions-item>
        <el-descriptions-item label="文件">{{ dataset.file_count }} 个，共 {{ formatSize(dataset.total_size) }}</el-descriptions-item>
        <el-descriptions-item label="当前版本"><span class="mono">{{ dataset.version.slice(0, 12) }}</span></el-descriptions-item>
        <el-descriptions-item label="说明"><pre class="pre">{{ dataset.description }}</pre></el-descriptions-item>
        <el-descriptions-item label="创建时间">{{ formatTime(dataset.created_at) }}</el-descriptions-item>
      </el-descriptions>
    </el-card>

    <el-card class="card">
      <template #header>
        <div class="actions">
          <span>文件</span>
          <span style="flex: 1" />
          <template v-if="isOwner">
            <input ref="picker" type="file" multiple hidden @change="onPick" />
            <el-button type="primary" :loading="uploading" @click="picker?.click()">上传文件</el-button>
          </template>
        </div>
      </template>
      <el-alert
        type="warning"
        :closable="false"
        show-icon
        class="notice"
        title="文件入库后只读：不能覆盖、修改或删除，同一数据集内文件名不能重复。可以继续追加文件，已提交的记录会记住提交时的版本。"
      />
      <el-alert
        v-if="versionFileIds"
        type="info"
        :closable="false"
        show-icon
        class="notice"
        :title="`正在查看版本 ${version.slice(0, 12)}：记录提交时有 ${versionFileIds.size} 个文件，标“提交后新增”的是之后上传的。`"
      />
      <div v-for="(u, i) in queue" :key="i" class="upload-item">
        <div class="upload-name">
          <span>{{ u.name }}（{{ formatSize(u.size) }}）</span>
          <span v-if="u.status === 'waiting'" class="muted">等待上传</span>
          <span v-else-if="u.status === 'done'" class="ok">已入库</span>
        </div>
        <el-progress v-if="u.status === 'uploading' || u.status === 'done'" :percentage="u.progress" :status="u.status === 'done' ? 'success' : undefined" />
        <el-alert v-if="u.status === 'error'" type="error" :title="`上传失败：${u.error}`" :closable="false" />
      </div>
      <el-table :data="files" empty-text="暂无文件">
        <el-table-column label="文件名" min-width="180">
          <template #default="{ row }">
            {{ row.name }}
            <el-tag v-if="versionFileIds && !versionFileIds.has(row.id)" class="status-tag" type="warning" disable-transitions>提交后新增</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="大小" min-width="90">
          <template #default="{ row }">{{ formatSize(row.size) }}</template>
        </el-table-column>
        <el-table-column label="SHA256" min-width="200" show-overflow-tooltip>
          <template #default="{ row }"><span class="mono">{{ row.sha256 }}</span></template>
        </el-table-column>
        <el-table-column label="上传人" min-width="90">
          <template #default="{ row }">{{ row.uploaded_by.name }}</template>
        </el-table-column>
        <el-table-column label="上传时间" min-width="140">
          <template #default="{ row }">{{ formatTime(row.uploaded_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" min-width="110" fixed="right">
          <template #default="{ row }">
            <div class="actions">
              <el-button v-if="previewKindOf(row.name)" link type="primary" @click="openPreview(row as DataFile)">预览</el-button>
              <el-link type="primary" :href="row.download_url">下载</el-link>
            </div>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
    <FilePreviewDialog v-model="previewOpen" :target="previewTarget" />
  </template>
</template>

<style scoped>
.notice {
  margin-bottom: 12px;
}
.upload-item {
  margin-bottom: 12px;
}
.upload-name {
  display: flex;
  gap: 12px;
  font-size: 14px;
  margin-bottom: 4px;
}
.muted {
  color: var(--el-text-color-secondary);
}
.ok {
  color: var(--el-color-success);
}
</style>

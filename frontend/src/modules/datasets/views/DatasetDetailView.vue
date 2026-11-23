<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Download, Edit } from '@element-plus/icons-vue'
import { datasetsApi, uploadFile } from '@/modules/datasets/api'
import type { DataFile, Dataset, DatasetReferences } from '@/api/types'
import { useAuthStore } from '@/stores/auth'
import { KIND_LABELS, formatSize, formatTime } from '@/utils/format'
import { errorMessage, showError, useFieldErrors } from '@/utils/errors'
import { previewKindOf } from '@/utils/preview'
import FilePreviewDialog, { type PreviewTarget } from '@/components/FilePreviewDialog.vue'
import PageHeader from '@/components/PageHeader.vue'
import IconButton from '@/components/IconButton.vue'
import FormDialog from '@/components/FormDialog.vue'
import StatusTag from '@/components/StatusTag.vue'

const RUN_ROLE_LABELS: Record<'input' | 'script' | 'output', string> = {
  input: '输入',
  script: '脚本',
  output: '结果',
}

const auth = useAuthStore()
const route = useRoute()
const router = useRouter()
const id = Number(route.params.id)

const dataset = ref<Dataset | null>(null)
const files = ref<DataFile[]>([])
const refs = ref<DatasetReferences>({ experiments: [], runs: [], reports: [] })
const loadError = ref('') // replaces the page; 404 reads 记录不存在或无权查看
const isOwner = computed(() => dataset.value?.owner.id === auth.user?.id)
const hasReferences = computed(
  () => refs.value.experiments.length > 0 || refs.value.runs.length > 0 || refs.value.reports.length > 0,
)
const canDelete = computed(() => isOwner.value && dataset.value?.file_count === 0 && !hasReferences.value)
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
    ;[dataset.value, files.value, refs.value] = await Promise.all([
      datasetsApi.get(id),
      datasetsApi.files(id),
      datasetsApi.references(id),
    ])
    if (version) versionFileIds.value = new Set((await datasetsApi.files(id, version)).map((f) => f.id))
  } catch (e) {
    loadError.value = errorMessage(e)
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
    ElMessage.success('数据集已删除')
    await router.push({ name: 'datasets' })
  } catch (e) {
    showError(e)
  } finally {
    deleting.value = false
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
          <IconButton
            v-if="dataset.file_count > 0"
            :icon="Download"
            label="打包下载 ZIP"
            tag="a"
            :href="datasetsApi.downloadZipUrl(dataset.id, version || undefined)"
          />
          <IconButton v-if="isOwner" :icon="Edit" label="编辑数据集" @click="openEdit" />
          <el-button v-if="canDelete" type="danger" plain :loading="deleting" @click="removeDataset">删除数据集</el-button>
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
          <span class="grow" />
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

    <el-card class="card" header="被引用处">
      <div v-if="!hasReferences" class="muted">暂无实验记录、数据处理记录或周报引用该数据集。</div>
      <div v-else class="refs">
        <section v-if="refs.experiments.length" class="ref-group">
          <div class="ref-title">实验记录（{{ refs.experiments.length }}）</div>
          <div class="ref-list">
            <div v-for="e in refs.experiments" :key="e.id" class="actions">
              <RouterLink :to="{ name: 'experiment-edit', params: { id: e.id } }">
                <span class="code">{{ e.code }}</span> {{ e.title }}
              </RouterLink>
              <StatusTag :status="e.status" />
            </div>
          </div>
        </section>
        <section v-if="refs.runs.length" class="ref-group">
          <div class="ref-title">数据处理记录（{{ refs.runs.length }}）</div>
          <div class="ref-list">
            <div v-for="r in refs.runs" :key="r.id" class="actions">
              <RouterLink :to="{ name: 'run-edit', params: { id: r.id } }">
                <span class="code">{{ r.code }}</span> {{ r.title }}
              </RouterLink>
              <el-tag v-for="role in r.roles" :key="role" size="small" type="info" disable-transitions>{{ RUN_ROLE_LABELS[role] }}</el-tag>
              <StatusTag :status="r.status" />
            </div>
          </div>
        </section>
        <section v-if="refs.reports.length" class="ref-group">
          <div class="ref-title">周报（{{ refs.reports.length }}）</div>
          <div class="ref-list">
            <div v-for="rep in refs.reports" :key="rep.id" class="actions">
              <RouterLink :to="{ name: 'report-edit', params: { id: rep.id } }">
                {{ rep.owner.name }} · {{ rep.week_start }} 这一周
              </RouterLink>
              <StatusTag :status="rep.status" />
            </div>
          </div>
        </section>
      </div>
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
  margin-bottom: 4px;
}
.ok {
  color: var(--el-color-success);
}
.refs {
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.ref-group {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.ref-title {
  color: var(--lab-text-3);
  font-weight: 600;
}
.ref-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
</style>

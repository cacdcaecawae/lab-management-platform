<script setup lang="ts">
import { computed, onBeforeUnmount, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Clock, Upload } from '@element-plus/icons-vue'
import { docsApi } from '../api'
import { equipmentApi } from '@/modules/equipment/api'
import type { DocCategory, DocDetail, DocWrite } from '@/api/types'
import { useOptions } from '@/composables/useOptions'
import { usePagedList } from '@/composables/usePagedList'
import { useLiveSearch } from '@/composables/useLiveSearch'
import { useSuggestions } from '@/api/suggestions'
import { useAuthStore } from '@/stores/auth'
import { DOC_CATEGORY_LABELS, formatSize, formatTime, mergeById } from '@/utils/format'
import { showActionError, showError, useFieldErrors } from '@/utils/errors'
import HistoryDrawer from '@/components/HistoryDrawer.vue'
import PageToolbar from '@/components/PageToolbar.vue'
import FormDialog from '@/components/FormDialog.vue'
import IconButton from '@/components/IconButton.vue'
import FilePreviewDialog, { type PreviewTarget } from '@/components/FilePreviewDialog.vue'
import { previewKindOf } from '@/utils/preview'

const auth = useAuthStore()
const route = useRoute()
const router = useRouter()

// ?equipment=<id> comes from the equipment page ("资料"), ?doc=<id> opens one document.
const routeEquipment = () => (Number(route.query.equipment) || '') as number | ''
const filters = reactive({ search: '', category: '', tag: '', equipment: routeEquipment() })
const tags = useSuggestions('doc.tags')
// another device's 资料, or 知识库 in the menu (no device), while the page is open: the view is reused
watch(() => route.query.equipment, () => (filters.equipment = routeEquipment()))
const keyword = useLiveSearch(filters)
const { items, count, page, pageSize, loading, load, sort } = usePagedList(docsApi.list, filters)
// shortcut: the first 100 devices; switch to remote search if the ledger grows past that.
const devices = useOptions(() => equipmentApi.list({ page_size: 100 }))
const previewOpen = ref(false)
const previewTarget = ref<PreviewTarget | null>(null)
function openPreview(file: { name: string; url: string; size?: number }) {
  previewTarget.value = { name: file.name, url: file.url, size: file.size }
  previewOpen.value = true
}

// ---- create / edit / detail dialog ----
const blank = (): DocWrite => ({ title: '', category: 'manual', equipment_id: null, tags: [], description: '' })
const form = reactive<DocWrite>(blank())
const errors = useFieldErrors(Object.keys(blank()))
const current = ref<DocDetail | null>(null)
const dialogOpen = ref(false)
const saving = ref(false)
const historyOpen = ref(false)
const detailLoading = ref(false)
const writer = computed(() => !current.value || current.value.author.id === auth.user?.id || auth.isManager)
const deviceOptions = computed(() => mergeById(devices.value, [current.value?.equipment]))

function fill(doc: DocDetail | null) {
  current.value = doc
  Object.assign(
    form,
    blank(),
    doc && { title: doc.title, category: doc.category, equipment_id: doc.equipment?.id ?? null, tags: [...doc.tags], description: doc.description },
  )
}

let detailGeneration = 0
onBeforeUnmount(() => { ++detailGeneration })

function resetDetail() {
  ++detailGeneration
  dialogOpen.value = false
  historyOpen.value = false
  detailLoading.value = false
  saving.value = false
  progress.value = null
  errors.clear()
  note.value = ''
  fill(null)
}

function closeDetail() {
  const routeDoc = route.query.doc
  resetDetail()
  if (routeDoc != null) {
    const query = { ...route.query }
    delete query.doc
    void router.replace({ query, hash: route.hash })
  }
}

function isCurrent(generation: number) {
  return generation === detailGeneration
}

async function openDoc(id: number | null) {
  resetDetail()
  const generation = detailGeneration
  detailLoading.value = id !== null
  try {
    const doc = id ? await docsApi.get(id) : null
    if (!isCurrent(generation)) return
    fill(doc)
    dialogOpen.value = true
  } catch (e) {
    if (isCurrent(generation)) showError(e)
  } finally {
    if (isCurrent(generation)) detailLoading.value = false
  }
}

async function openFromList(id: number | null) {
  const next = id === null ? undefined : String(id)
  if (route.query.doc === next) return openDoc(id)
  const query = { ...route.query }
  if (next) query.doc = next
  else delete query.doc
  await router.replace({ query, hash: route.hash })
  if (next === undefined && route.query.doc === undefined) return openDoc(null)
}

async function save() {
  if (saving.value) return
  const generation = detailGeneration
  const id = current.value?.id
  const payload = { ...form, tags: [...form.tags] }
  saving.value = true
  try {
    const saved = id ? await docsApi.update(id, payload) : await docsApi.create(payload)
    load()
    if (!isCurrent(generation)) return
    fill(saved)
    ElMessage.success(id ? '已保存' : '已新建，可以上传文件')
    errors.clear()
  } catch (e) {
    if (isCurrent(generation)) errors.handle(e)
  } finally {
    if (isCurrent(generation)) saving.value = false
  }
}

async function remove() {
  const doc = current.value
  const generation = detailGeneration
  if (!doc) return
  try {
    await ElMessageBox.confirm(`删除“${doc.title}”及它的全部 ${doc.versions.length} 个版本？删除后无法恢复。`, '删除文档', { type: 'warning' })
  } catch {
    return
  }
  if (!isCurrent(generation)) return
  try {
    await docsApi.remove(doc.id)
    load()
    if (!isCurrent(generation)) return
    ElMessage.success('已删除')
    closeDetail()
  } catch (e) {
    if (isCurrent(generation)) showActionError(e)
  }
}

// ---- versions ----
const picker = ref<HTMLInputElement>()
const note = ref('')
const progress = ref<number | null>(null)

async function onPick(e: Event) {
  const input = e.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = '' // allow picking the same file again after an error
  const id = current.value?.id
  const generation = detailGeneration
  if (!file || !id || progress.value !== null) return
  progress.value = 0
  try {
    const version = await docsApi.addVersion(id, file, note.value, (p) => {
      if (isCurrent(generation)) progress.value = p
    })
    load()
    if (!isCurrent(generation)) return
    ElMessage.success(`已上传第 ${version.number} 版`)
    note.value = ''
    const doc = await docsApi.get(id)
    if (isCurrent(generation)) fill(doc)
  } catch (err) {
    if (isCurrent(generation)) showActionError(err)
  } finally {
    if (isCurrent(generation)) progress.value = null
  }
}

watch(() => route.query.doc, (doc, previous) => {
  if (typeof doc === 'string' && /^\d+$/.test(doc) && Number.isSafeInteger(Number(doc)) && Number(doc) > 0) {
    void openDoc(Number(doc))
  } else if (previous != null) {
    resetDetail()
  }
}, { immediate: true })
</script>

<template>
  <el-card class="card">
    <p v-if="detailLoading" role="status">正在加载文档…</p>
    <PageToolbar>
      <el-input v-model="keyword" placeholder="搜索标题、标签、说明、设备" clearable @change="filters.search = keyword" />
      <el-select v-model="filters.category" placeholder="全部分类" aria-label="分类" clearable>
        <el-option v-for="(label, k) in DOC_CATEGORY_LABELS" :key="k" :label="label" :value="k" />
      </el-select>
      <el-select v-model="filters.equipment" placeholder="全部设备" aria-label="设备" clearable filterable>
        <el-option v-for="d in devices" :key="d.id" :label="`${d.code} ${d.name}`" :value="d.id" />
      </el-select>
      <el-select v-model="filters.tag" placeholder="全部标签" aria-label="标签" clearable filterable remote :remote-method="tags.search">
        <el-option v-for="t in tags.values.value" :key="t" :label="t" :value="t" />
      </el-select>
      <template #actions>
        <el-button type="primary" @click="openFromList(null)">新建文档</el-button>
      </template>
    </PageToolbar>
    <el-table @sort-change="sort" v-loading="loading" :data="items" empty-text="没有符合条件的文档">
      <el-table-column label="标题" min-width="200">
        <template #default="{ row }"><el-button link type="primary" @click="openFromList(row.id)">{{ row.title }}</el-button></template>
      </el-table-column>
      <el-table-column label="分类" min-width="90">
        <template #default="{ row }">{{ DOC_CATEGORY_LABELS[row.category] }}</template>
      </el-table-column>
      <el-table-column label="关联设备" min-width="150">
        <template #default="{ row }">{{ row.equipment ? `${row.equipment.code} ${row.equipment.name}` : '' }}</template>
      </el-table-column>
      <el-table-column label="标签" min-width="140">
        <template #default="{ row }">
          <el-tag v-for="t in row.tags" :key="t" size="small" class="tag" disable-transitions role="button" tabindex="0" :title="`只看标签“${t}”`" @click="filters.tag = t" @keydown.enter="filters.tag = t">{{ t }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="最新文件" min-width="180">
        <template #default="{ row }">
          <template v-if="row.latest">
            <el-button v-if="previewKindOf(row.latest.name)" link type="primary" @click="openPreview(row.latest)">{{ row.latest.name }}</el-button>
            <a v-else :href="row.latest.url" target="_blank" rel="noopener">{{ row.latest.name }}</a>
            <span class="muted"> 第 {{ row.latest.number }} 版</span>
          </template>
        </template>
      </el-table-column>
      <el-table-column label="作者" min-width="80">
        <template #default="{ row }">{{ row.author.name }}</template>
      </el-table-column>
      <el-table-column label="更新时间" prop="updated_at" sortable="custom" min-width="140">
        <template #default="{ row }">{{ formatTime(row.updated_at) }}</template>
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
  </el-card>

  <FormDialog :model-value="dialogOpen" :before-close="closeDetail" :title="current ? current.title : '新建文档'" :readonly="!writer" :loading="saving" @submit="save">
    <template #before>
      <div v-if="current" class="meta-line">
        <span>{{ current.author.name }} 创建于 {{ formatTime(current.created_at) }}</span>
        <IconButton :icon="Clock" label="修改历史" @click="historyOpen = true" />
      </div>
    </template>
    <el-form-item label="标题" :error="errors.fe('title')" required><el-input v-model="form.title" /></el-form-item>
    <div class="form-grid">
      <el-form-item label="分类" :error="errors.fe('category')" required>
        <el-select v-model="form.category">
          <el-option v-for="(label, k) in DOC_CATEGORY_LABELS" :key="k" :label="label" :value="k as DocCategory" />
        </el-select>
      </el-form-item>
      <el-form-item class="span-2" label="关联设备" :error="errors.fe('equipment_id')">
        <el-select v-model="form.equipment_id" filterable clearable placeholder="可不选">
          <el-option v-for="d in deviceOptions" :key="d.id" :label="`${d.code} ${d.name}`" :value="d.id" />
        </el-select>
      </el-form-item>
    </div>
    <el-form-item label="标签" :error="errors.fe('tags')">
      <el-select v-model="form.tags" multiple filterable allow-create default-first-option :reserve-keyword="false" placeholder="输入后回车，可多个" @visible-change="(open: boolean) => open && tags.search()">
        <el-option v-for="t in tags.values.value" :key="t" :label="t" :value="t" />
      </el-select>
    </el-form-item>
    <el-form-item label="说明" :error="errors.fe('description')">
      <el-input v-model="form.description" type="textarea" :autosize="{ minRows: 3, maxRows: 12 }" placeholder="用途、适用版本、注意事项；调试经验可以直接写在这里" />
    </el-form-item>
    <el-alert v-for="msg in errors.others.value" :key="msg" :title="msg" type="error" :closable="false" />
    <template #after>
      <template v-if="current">
        <div class="section-title">文件版本</div>
        <ul v-if="current.versions.length" class="versions">
          <li v-for="v in current.versions" :key="v.id">
            <span class="version-no">第 {{ v.number }} 版</span>
            <el-button v-if="previewKindOf(v.name)" link type="primary" class="name" @click="openPreview(v)">{{ v.name }}</el-button>
            <a v-else :href="v.url" target="_blank" rel="noopener" class="name">{{ v.name }}</a>
            <span class="muted">{{ formatSize(v.size) }} · {{ v.uploaded_by.name }} · {{ formatTime(v.created_at) }}</span>
            <a v-if="previewKindOf(v.name)" :href="v.url" :download="v.name" class="muted">下载</a>
            <span v-if="v.note" class="note">{{ v.note }}</span>
            <span class="mono muted" :title="`SHA256 ${v.sha256}`">{{ v.sha256.slice(0, 12) }}</span>
          </li>
        </ul>
        <p v-else class="muted">暂无文件</p>
        <div v-if="writer" class="add">
          <el-input v-model="note" class="version-note" placeholder="本版说明（可不填），如 适配新固件" maxlength="200" />
          <el-button :icon="Upload" :loading="progress !== null" @click="picker?.click()">
            {{ current.versions.length ? '上传新版本' : '上传文件' }}
          </el-button>
          <input ref="picker" type="file" hidden @change="onPick" />
        </div>
        <el-progress v-if="progress !== null" :percentage="progress" />
        <p v-if="writer && current.versions.length" class="muted">上传新版本不会覆盖旧版本，旧版本都还能下载。</p>
      </template>
    </template>
    <template #extra>
      <el-button v-if="current && auth.isManager" type="danger" plain @click="remove">删除文档</el-button>
    </template>
  </FormDialog>
  <FilePreviewDialog v-model="previewOpen" :target="previewTarget" />

  <HistoryDrawer
    v-if="current"
    v-model="historyOpen"
    :load="() => docsApi.history(current!.id)"
    :values="{ category: DOC_CATEGORY_LABELS }"
    :labels="{ title: '标题', category: '分类', equipment: '关联设备' }"
  />
</template>

<style scoped>
.tag {
  margin: 0 4px 2px 0;
  cursor: pointer;
}
.muted {
  color: var(--lab-text-3);
  font-size: 13px;
}
.meta-line {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
  color: var(--lab-text-3);
  font-size: 13px;
}
.section-title {
  margin: 16px 0 8px;
  font-weight: 500;
}
.versions {
  margin: 0;
  padding: 0;
  list-style: none;
}
.versions li {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 4px 10px;
  padding: 8px 0;
  border-bottom: 1px solid var(--lab-border);
}
.version-no {
  font-weight: 500;
}
.name {
  min-width: 0;
  overflow-wrap: anywhere;
}
.note {
  flex-basis: 100%;
  font-size: 13px;
}
.add {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 12px;
}
.version-note {
  flex: 1;
  min-width: 200px;
}
.left {
  float: left;
}
</style>

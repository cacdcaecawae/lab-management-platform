<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Upload } from '@element-plus/icons-vue'
import { docsApi } from '../api'
import { equipmentApi } from '@/modules/equipment/api'
import type { DocCategory, DocDetail, DocWrite } from '@/api/types'
import { useOptions } from '@/composables/useOptions'
import { usePagedList } from '@/composables/usePagedList'
import { useAuthStore } from '@/stores/auth'
import { DOC_CATEGORY_LABELS, formatSize, formatTime, mergeById } from '@/utils/format'
import { showActionError, showError, useFieldErrors } from '@/utils/errors'
import HistoryDrawer from '@/components/HistoryDrawer.vue'

const auth = useAuthStore()
const route = useRoute()

// ?equipment=<id> comes from the equipment page ("资料"), ?doc=<id> opens one document.
const initialEquipment = Number(route.query.equipment) || ''
const filters = reactive({ search: '', category: '', equipment: initialEquipment as number | '' })
const keyword = ref('')
const { items, count, page, pageSize, loading, load } = usePagedList(docsApi.list, filters)
// shortcut: the first 100 devices; switch to remote search if the ledger grows past that.
const devices = useOptions(() => equipmentApi.list({ page_size: 100 }))

// ---- create / edit / detail dialog ----
const blank = (): DocWrite => ({ title: '', category: 'manual', equipment_id: null, tags: [], description: '' })
const form = reactive<DocWrite>(blank())
const errors = useFieldErrors(Object.keys(blank()))
const current = ref<DocDetail | null>(null)
const dialogOpen = ref(false)
const saving = ref(false)
const historyOpen = ref(false)
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

async function openDoc(id: number | null) {
  errors.clear()
  note.value = ''
  try {
    fill(id ? await docsApi.get(id) : null)
    dialogOpen.value = true
  } catch (e) {
    showError(e)
  }
}
async function save() {
  saving.value = true
  try {
    if (current.value) {
      fill(await docsApi.update(current.value.id, form))
      ElMessage.success('已保存')
    } else {
      fill(await docsApi.create(form))
      ElMessage.success('已新建，可以上传文件')
    }
    errors.clear()
    load()
  } catch (e) {
    errors.handle(e)
  } finally {
    saving.value = false
  }
}

async function remove() {
  const doc = current.value!
  try {
    await ElMessageBox.confirm(`删除“${doc.title}”及它的全部 ${doc.versions.length} 个版本？删除后无法恢复。`, '删除文档', { type: 'warning' })
  } catch {
    return
  }
  try {
    await docsApi.remove(doc.id)
    ElMessage.success('已删除')
    dialogOpen.value = false
    load()
  } catch (e) {
    showActionError(e)
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
  if (!file || !current.value) return
  progress.value = 0
  try {
    const version = await docsApi.addVersion(current.value.id, file, note.value, (p) => (progress.value = p))
    ElMessage.success(`已上传第 ${version.number} 版`)
    note.value = ''
    fill(await docsApi.get(current.value.id))
    load()
  } catch (err) {
    showActionError(err)
  } finally {
    progress.value = null
  }
}

if (Number(route.query.doc)) openDoc(Number(route.query.doc)) // after `note` above exists
</script>

<template>
  <el-card class="card">
    <div class="page-toolbar">
      <el-input v-model="keyword" placeholder="搜索标题、标签、说明、设备" clearable @change="filters.search = keyword" />
      <el-select v-model="filters.category" placeholder="全部分类" aria-label="分类" clearable>
        <el-option v-for="(label, k) in DOC_CATEGORY_LABELS" :key="k" :label="label" :value="k" />
      </el-select>
      <el-select v-model="filters.equipment" placeholder="全部设备" aria-label="设备" clearable filterable>
        <el-option v-for="d in devices" :key="d.id" :label="`${d.code} ${d.name}`" :value="d.id" />
      </el-select>
      <span class="grow" />
      <el-button type="primary" @click="openDoc(null)">新建文档</el-button>
    </div>
    <el-table v-loading="loading" :data="items" empty-text="没有符合条件的文档">
      <el-table-column label="标题" min-width="200">
        <template #default="{ row }"><el-button link type="primary" @click="openDoc(row.id)">{{ row.title }}</el-button></template>
      </el-table-column>
      <el-table-column label="分类" min-width="90">
        <template #default="{ row }">{{ DOC_CATEGORY_LABELS[row.category] }}</template>
      </el-table-column>
      <el-table-column label="关联设备" min-width="150">
        <template #default="{ row }">{{ row.equipment ? `${row.equipment.code} ${row.equipment.name}` : '' }}</template>
      </el-table-column>
      <el-table-column label="标签" min-width="140">
        <template #default="{ row }">
          <el-tag v-for="t in row.tags" :key="t" size="small" class="tag" disable-transitions>{{ t }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="最新文件" min-width="180">
        <template #default="{ row }">
          <a v-if="row.latest" :href="row.latest.url" target="_blank" rel="noopener">{{ row.latest.name }}</a>
          <span v-if="row.latest" class="muted"> 第 {{ row.latest.number }} 版</span>
        </template>
      </el-table-column>
      <el-table-column label="作者" min-width="80">
        <template #default="{ row }">{{ row.author.name }}</template>
      </el-table-column>
      <el-table-column label="更新时间" min-width="140">
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

  <el-dialog v-model="dialogOpen" :title="current ? current.title : '新建文档'" width="min(640px, 95vw)">
    <div v-if="current" class="meta-line">
      <span>{{ current.author.name }} 创建于 {{ formatTime(current.created_at) }}</span>
      <el-button link @click="historyOpen = true">修改历史</el-button>
    </div>
    <el-form label-position="top" :disabled="!writer" @submit.prevent="save">
      <el-form-item label="标题" :error="errors.fe('title')" required><el-input v-model="form.title" /></el-form-item>
      <el-row :gutter="12">
        <el-col :xs="24" :sm="10">
          <el-form-item label="分类" :error="errors.fe('category')" required>
            <el-select v-model="form.category">
              <el-option v-for="(label, k) in DOC_CATEGORY_LABELS" :key="k" :label="label" :value="k as DocCategory" />
            </el-select>
          </el-form-item>
        </el-col>
        <el-col :xs="24" :sm="14">
          <el-form-item label="关联设备" :error="errors.fe('equipment_id')">
            <el-select v-model="form.equipment_id" filterable clearable placeholder="可不选">
              <el-option v-for="d in deviceOptions" :key="d.id" :label="`${d.code} ${d.name}`" :value="d.id" />
            </el-select>
          </el-form-item>
        </el-col>
      </el-row>
      <el-form-item label="标签" :error="errors.fe('tags')">
        <el-select v-model="form.tags" multiple filterable allow-create default-first-option :reserve-keyword="false" placeholder="输入后回车，可多个" />
      </el-form-item>
      <el-form-item label="说明" :error="errors.fe('description')">
        <el-input v-model="form.description" type="textarea" :autosize="{ minRows: 3, maxRows: 12 }" placeholder="用途、适用版本、注意事项；调试经验可以直接写在这里" />
      </el-form-item>
      <el-alert v-for="msg in errors.others.value" :key="msg" :title="msg" type="error" :closable="false" />
    </el-form>

    <template v-if="current">
      <div class="section-title">文件版本</div>
      <ul v-if="current.versions.length" class="versions">
        <li v-for="v in current.versions" :key="v.id">
          <span class="version-no">第 {{ v.number }} 版</span>
          <a :href="v.url" target="_blank" rel="noopener" class="name">{{ v.name }}</a>
          <span class="muted">{{ formatSize(v.size) }} · {{ v.uploaded_by.name }} · {{ formatTime(v.created_at) }}</span>
          <span v-if="v.note" class="note">{{ v.note }}</span>
          <span class="mono muted" :title="`SHA256 ${v.sha256}`">{{ v.sha256.slice(0, 12) }}</span>
        </li>
      </ul>
      <p v-else class="muted">还没有文件</p>
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

    <template #footer>
      <el-button v-if="current && auth.isManager" type="danger" plain class="left" @click="remove">删除文档</el-button>
      <el-button @click="dialogOpen = false">{{ writer ? '取消' : '关闭' }}</el-button>
      <el-button v-if="writer" type="primary" :loading="saving" @click="save">保存</el-button>
    </template>
  </el-dialog>

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
}
.muted {
  color: var(--lab-text-3);
  font-size: 12.5px;
}
.meta-line {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
  color: var(--lab-text-3);
  font-size: 12.5px;
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

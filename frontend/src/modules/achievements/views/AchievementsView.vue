<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Clock, Download, Histogram, Upload } from '@element-plus/icons-vue'
import { achievementsApi } from '@/modules/achievements/api'
import { membersApi } from '@/modules/members/api'
import type { Achievement, AchievementStatus, AchievementType, AchievementWrite } from '@/api/types'
import { useOptions } from '@/composables/useOptions'
import { usePagedList } from '@/composables/usePagedList'
import { useAuthStore } from '@/stores/auth'
import {
  ACHIEVEMENT_STATUSES,
  ACHIEVEMENT_STATUS_LABELS,
  ACHIEVEMENT_TYPE_LABELS,
  VENUE_LABELS,
  formatTime,
  mergeById,
  toDateStr,
} from '@/utils/format'
import { showActionError, showError, useFieldErrors } from '@/utils/errors'
import HistoryDrawer from '@/components/HistoryDrawer.vue'
import AchievementStatsPanel from './AchievementStatsPanel.vue'
import PageToolbar from '@/components/PageToolbar.vue'
import FormDialog from '@/components/FormDialog.vue'
import IconButton from '@/components/IconButton.vue'
import FilePreviewDialog, { type PreviewTarget } from '@/components/FilePreviewDialog.vue'

const auth = useAuthStore()
// the export answers with an attachment, so the page stays where it is
const download = (url: string) => window.location.assign(url)
const previewOpen = ref(false)
const previewTarget = ref<PreviewTarget | null>(null)
function openPdf(name: string, url: string) {
  previewTarget.value = { name: name || '全文.pdf', url }
  previewOpen.value = true
}
const statsOpen = ref(false)
const route = useRoute()
const router = useRouter()
const routeItem = () => typeof route.query.item === 'string' ? route.query.item : ''
const thisYear = new Date().getFullYear()
const years = Array.from({ length: 10 }, (_, i) => thisYear - i)

// "已录用及以上" is what most applications ask for: accepted and published papers.
const STATUS_FILTERS: Record<string, string> = { formal: '正式成果（按类型）', 'accepted,published': '已录用（含已发表）', ...ACHIEVEMENT_STATUS_LABELS }
const filters = reactive({ item: routeItem(), search: '', type: '', year: '' as number | '', status: '', member: '' as number | '' })
const keyword = ref('')
watch(routeItem, (item) => { filters.item = item })
function showAll() {
  const query = { ...route.query }
  delete query.item
  return router.replace({ query, hash: route.hash })
}
const { items, count, page, pageSize, loading, load } = usePagedList(achievementsApi.list, filters)
const members = useOptions(() => membersApi.list({ page_size: 100 })) // former members too: they stay authors
const exportQuery = computed(() => ({ ...filters }))

// ---- dialog ----
const blank = (): AchievementWrite => ({
  type: 'paper', title: '', authors: '', member_ids: [], venue: '', date: toDateStr(new Date()), status: 'submitted', link: '', notes: '',
})
const form = reactive<AchievementWrite>(blank())
const errors = useFieldErrors(Object.keys(blank()))
const current = ref<Achievement | null>(null)
const dialogOpen = ref(false)
const saving = ref(false)
const historyOpen = ref(false)
const writer = computed(
  () => !current.value || current.value.created_by.id === auth.user?.id || current.value.members.some((m) => m.id === auth.user?.id) || auth.isManager,
)
const memberOptions = computed(() => mergeById(members.value, current.value?.members ?? []))
const statusOptions = computed(() => ACHIEVEMENT_STATUSES[form.type])
// A type has its own statuses: switching the type picks its first one when the old one no longer fits.
watch(
  () => form.type,
  (t) => {
    if (!ACHIEVEMENT_STATUSES[t].includes(form.status)) form.status = ACHIEVEMENT_STATUSES[t][0] as AchievementStatus
  },
)

// Opening another record makes answers for the one before stale: they must not land on this one.
let dialogGen = 0

function open(a: Achievement | null) {
  dialogGen++
  current.value = a
  Object.assign(form, blank(), a && { ...a, member_ids: a.members.map((m) => m.id) })
  errors.clear()
  dialogOpen.value = true
}

async function save() {
  const gen = dialogGen
  saving.value = true
  try {
    const { type, title, authors, member_ids, venue, date, status, link, notes } = form
    const body = { type, title, authors, member_ids, venue, date, status, link, notes }
    const saved = current.value ? await achievementsApi.update(current.value.id, body) : await achievementsApi.create(body)
    ElMessage.success(saved.fulltext_name ? '已保存' : '已保存，可以上传全文')
    load()
    if (gen !== dialogGen) return
    current.value = saved
    errors.clear()
  } catch (e) {
    if (gen === dialogGen) errors.handle(e)
    else showError(e)
  } finally {
    saving.value = false
  }
}

async function remove() {
  try {
    await ElMessageBox.confirm(`删除“${current.value!.title}”？删除后无法恢复。`, '删除成果', { type: 'warning' })
  } catch {
    return
  }
  try {
    await achievementsApi.remove(current.value!.id)
    ElMessage.success('已删除')
    dialogOpen.value = false
    load()
  } catch (e) {
    showActionError(e)
  }
}

// ---- full text ----
const picker = ref<HTMLInputElement>()
const uploading = ref(false)

async function onPick(e: Event) {
  const input = e.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file || !current.value) return
  const gen = dialogGen
  uploading.value = true
  try {
    const saved = await achievementsApi.uploadFulltext(current.value.id, file)
    ElMessage.success('全文已上传')
    load()
    if (gen === dialogGen) current.value = saved
  } catch (err) {
    showActionError(err) // e.g. 只支持 PDF
  } finally {
    uploading.value = false
  }
}

async function removeFulltext() {
  const gen = dialogGen
  try {
    await ElMessageBox.confirm('删除已上传的全文？', '删除全文', { type: 'warning' })
    await achievementsApi.removeFulltext(current.value!.id)
    if (gen === dialogGen) current.value = { ...current.value!, fulltext_name: '', fulltext_url: null }
    load()
  } catch (e) {
    if (e !== 'cancel' && e !== 'close') showError(e)
  }
}
</script>

<template>
  <el-card class="card">
    <PageToolbar>
      <el-button v-if="filters.item" @click="showAll">显示全部</el-button>
      <el-input v-model="keyword" placeholder="搜索标题、作者、出处" clearable @change="filters.search = keyword" />
      <el-select v-model="filters.type" placeholder="全部类型" aria-label="类型" clearable>
        <el-option v-for="(label, k) in ACHIEVEMENT_TYPE_LABELS" :key="k" :label="label" :value="k" />
      </el-select>
      <el-select v-model="filters.year" placeholder="全部年份" aria-label="年份" clearable>
        <el-option v-for="y in years" :key="y" :label="`${y} 年`" :value="y" />
      </el-select>
      <el-select v-model="filters.status" placeholder="全部状态" aria-label="状态" clearable>
        <el-option v-for="(label, k) in STATUS_FILTERS" :key="k" :label="label" :value="k" />
      </el-select>
      <el-select v-model="filters.member" placeholder="全部成员" aria-label="成员" clearable filterable>
        <el-option v-for="m in members" :key="m.id" :label="m.name" :value="m.id" />
      </el-select>
      <template #actions>
        <IconButton :icon="Histogram" label="成果统计" @click="statsOpen = true" />
        <el-dropdown trigger="click" @command="(kind: string) => download(achievementsApi.exportUrl(exportQuery, kind === 'files'))">
          <el-button class="icon-only" :icon="Download" text circle aria-label="导出" />
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="excel">导出 Excel</el-dropdown-item>
              <el-dropdown-item command="files">导出（附全文）</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <el-button type="primary" @click="open(null)">登记成果</el-button>
      </template>
    </PageToolbar>
    <el-table v-loading="loading" :data="items" empty-text="没有符合条件的成果">
      <el-table-column label="标题" min-width="240">
        <template #default="{ row }"><el-button link type="primary" class="title" @click="open(row as Achievement)">{{ row.title }}</el-button></template>
      </el-table-column>
      <el-table-column label="类型" min-width="70">
        <template #default="{ row }">{{ ACHIEVEMENT_TYPE_LABELS[row.type] }}</template>
      </el-table-column>
      <el-table-column prop="authors" label="作者" min-width="160" show-overflow-tooltip />
      <el-table-column prop="venue" label="出处 / 编号" min-width="160" show-overflow-tooltip />
      <el-table-column prop="date" label="日期" min-width="100" />
      <el-table-column label="状态" min-width="80">
        <template #default="{ row }">{{ ACHIEVEMENT_STATUS_LABELS[row.status] }}</template>
      </el-table-column>
      <el-table-column label="全文" min-width="70">
        <template #default="{ row }">
          <el-button v-if="row.fulltext_url" link type="primary" @click="openPdf(row.fulltext_name || `${row.title}.pdf`, row.fulltext_url)">PDF</el-button>
        </template>
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

  <FormDialog v-model="dialogOpen" :title="current ? '成果' : '登记成果'" :readonly="!writer" :loading="saving" @submit="save">
    <template #before>
      <div v-if="current" class="meta-line">
        <span>{{ current.created_by.name }} 登记于 {{ formatTime(current.created_at) }}</span>
        <IconButton :icon="Clock" label="修改历史" @click="historyOpen = true" />
      </div>
    </template>
    <div class="form-grid">
      <el-form-item label="类型" :error="errors.fe('type')" required>
        <el-select v-model="form.type">
          <el-option v-for="(label, k) in ACHIEVEMENT_TYPE_LABELS" :key="k" :label="label" :value="k as AchievementType" />
        </el-select>
      </el-form-item>
      <el-form-item label="状态" :error="errors.fe('status')" required>
        <el-select v-model="form.status">
          <el-option v-for="s in statusOptions" :key="s" :label="ACHIEVEMENT_STATUS_LABELS[s]" :value="s" />
        </el-select>
      </el-form-item>
      <el-form-item label="日期" :error="errors.fe('date')" required>
        <el-date-picker v-model="form.date" type="date" value-format="YYYY-MM-DD" :clearable="false" />
      </el-form-item>
    </div>
    <el-form-item label="标题" :error="errors.fe('title')" required><el-input v-model="form.title" /></el-form-item>
    <el-form-item label="作者（按署名顺序，含外单位）" :error="errors.fe('authors')" required>
      <el-input v-model="form.authors" placeholder="如 张三, 李四, 王五" />
    </el-form-item>
    <el-form-item label="本组成员" :error="errors.fe('member_ids')">
      <el-select v-model="form.member_ids" multiple filterable placeholder="署名里的本组成员，用于按人查找">
        <el-option v-for="m in memberOptions" :key="m.id" :label="m.name" :value="m.id" />
      </el-select>
    </el-form-item>
    <el-form-item :label="VENUE_LABELS[form.type]" :error="errors.fe('venue')"><el-input v-model="form.venue" /></el-form-item>
    <el-form-item label="DOI / 链接" :error="errors.fe('link')"><el-input v-model="form.link" /></el-form-item>
    <el-form-item label="备注" :error="errors.fe('notes')">
      <el-input v-model="form.notes" type="textarea" :autosize="{ minRows: 2 }" />
    </el-form-item>
    <el-alert v-for="msg in errors.others.value" :key="msg" :title="msg" type="error" :closable="false" />
    <template #after>
      <template v-if="current">
        <div class="section-title">全文（PDF）</div>
        <div class="fulltext">
          <template v-if="current.fulltext_url">
            <el-button link type="primary" @click="openPdf(current.fulltext_name || `${current.title}.pdf`, current.fulltext_url)">
              {{ current.fulltext_name || '全文.pdf' }}
            </el-button>
            <a :href="current.fulltext_url" :download="current.fulltext_name || '全文.pdf'" class="muted">下载</a>
          </template>
          <span v-else class="muted">暂未上传</span>
          <template v-if="writer">
            <el-button :icon="Upload" :loading="uploading" @click="picker?.click()">{{ current.fulltext_url ? '替换全文' : '上传全文' }}</el-button>
            <el-button v-if="current.fulltext_url" link type="danger" @click="removeFulltext">删除全文</el-button>
            <input ref="picker" type="file" accept=".pdf" hidden @change="onPick" />
          </template>
        </div>
      </template>
    </template>
    <template #extra>
      <el-button v-if="current && auth.isManager" type="danger" plain @click="remove">删除成果</el-button>
    </template>
  </FormDialog>
  <FilePreviewDialog v-model="previewOpen" :target="previewTarget" />

  <HistoryDrawer
    v-if="current"
    v-model="historyOpen"
    :load="() => achievementsApi.history(current!.id)"
    :values="{ type: ACHIEVEMENT_TYPE_LABELS, status: ACHIEVEMENT_STATUS_LABELS }"
    :labels="{ title: '标题', type: '类型' }"
  />
  <el-dialog v-model="statsOpen" title="成果统计" width="min(900px, 95vw)" destroy-on-close>
    <AchievementStatsPanel v-if="statsOpen" />
  </el-dialog>
</template>

<style scoped>
.title {
  white-space: normal;
  text-align: left;
  height: auto;
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
.fulltext {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px;
}
.muted {
  color: var(--lab-text-3);
}
.left {
  float: left;
}
</style>

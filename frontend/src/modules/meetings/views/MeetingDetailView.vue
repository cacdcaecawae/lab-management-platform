<script setup lang="ts">
import { replaceSavedEditor } from '@/router/saved-editor'
import { computed, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Clock, Delete, Plus } from '@element-plus/icons-vue'
import { meetingsApi } from '@/modules/meetings/api'
import { membersApi } from '@/modules/members/api'
import { ApiError } from '@/api/client'
import type { ActionItem, Meeting, MeetingWrite } from '@/api/types'
import { useOptions } from '@/composables/useOptions'
import { useAuthStore } from '@/stores/auth'
import { formatTime, mergeById, toDateStr } from '@/utils/format'
import { errorMessage, showActionError, showError, useFieldErrors } from '@/utils/errors'
import AttachmentList from '@/components/AttachmentList.vue'
import HistoryDrawer from '@/components/HistoryDrawer.vue'
import PageHeader from '@/components/PageHeader.vue'
import { closeTab } from '@/layouts/nav'
import { useUnsavedGuard } from '@/composables/useUnsavedGuard'
import IconButton from '@/components/IconButton.vue'

const auth = useAuthStore()
const route = useRoute()
const router = useRouter()

const meeting = ref<Meeting | null>(null)
const loadError = ref('')
const editing = ref(false)
const saving = ref(false)
const historyOpen = ref(false)
const members = useOptions(() => membersApi.list({ is_active: true, page_size: 100 }))
// Former members stay selectable on the meeting they were part of.
const memberOptions = computed(() =>
  mergeById(members.value, [
    ...(meeting.value?.agenda.map((a) => a.presenter) ?? []), ...(meeting.value?.actions.map((a) => a.owner) ?? []), meeting.value?.recorder,
  ]),
)
// Supervisors edit everything; the meeting's recorder (students take the minutes in turn) its minutes and action items.
const isRecorder = computed(() => !!meeting.value?.recorder && meeting.value.recorder.id === auth.user?.id)
const canEdit = computed(() => auth.isSupervisor || isRecorder.value)
const today = toDateStr(new Date())
const overdue = (a: ActionItem) => !a.done_at && !!a.due_date && a.due_date < today

// ---- edit form ----
interface Row {
  id?: number
  person: number | null
  text: string
  due_date: string | null
  carried_from?: number
}
// A new meeting's minutes start from this outline (edit or delete freely); it is not stored anywhere else.
const MINUTES_OUTLINE = '本周进展：\n\n讨论：\n\n决定：\n\n下周安排：\n'
const form = reactive({
  date: today, time: null as string | null, location: '', title: '组会', recorder: null as number | null, minutes: '',
  agenda: [] as Row[], actions: [] as Row[],
})
const errors = useFieldErrors(['date', 'time', 'location', 'title', 'recorder_id', 'minutes', 'agenda', 'actions'])
// Ask before leaving with unsaved changes while editing (startEdit() takes the snapshot).
const { markSaved } = useUnsavedGuard(form, () => editing.value)

function startEdit() {
  const m = meeting.value
  Object.assign(form, {
    date: m?.date ?? today,
    time: m?.time ?? null,
    location: m?.location ?? '',
    title: m?.title ?? '组会',
    recorder: m?.recorder?.id ?? null,
    minutes: m ? m.minutes : MINUTES_OUTLINE,
    agenda: m ? m.agenda.map((a) => ({ person: a.presenter.id, text: a.topic, due_date: null })) : [{ person: null, text: '', due_date: null }],
    actions: m ? m.actions.map((a) => ({ id: a.id, person: a.owner.id, text: a.content, due_date: a.due_date })) : [],
  })
  errors.clear()
  editing.value = true
  markSaved()
}

function body(): Partial<MeetingWrite> {
  const filled = (r: Row) => r.person !== null || r.text.trim() // an untouched blank row is not sent
  const notes = {
    minutes: form.minutes,
    actions: form.actions
      .filter(filled)
      .map((r) => ({ id: r.id, owner_id: r.person!, content: r.text, due_date: r.due_date || null, carried_from: r.carried_from })),
  }
  if (!auth.isSupervisor) return notes // the recorder may send only these
  return {
    ...notes,
    date: form.date,
    time: form.time || null,
    location: form.location,
    title: form.title,
    recorder_id: form.recorder,
    agenda: form.agenda.filter(filled).map((r) => ({ presenter_id: r.person!, topic: r.text })),
  }
}

async function save() {
  saving.value = true
  try {
    const source = router.currentRoute?.value
    const saved = meeting.value ? await meetingsApi.update(meeting.value.id, body()) : await meetingsApi.create(body() as MeetingWrite)
    ElMessage.success('已保存')
    editing.value = false
    if (!meeting.value && source) void replaceSavedEditor(router, source, { name: 'meeting-detail', params: { id: saved.id } })
    meeting.value = saved
  } catch (e) {
    errors.handle(e) // row errors arrive as agenda / actions lists and show under the section
  } finally {
    saving.value = false
  }
}

async function remove() {
  try {
    await ElMessageBox.confirm(`删除 ${meeting.value!.date} 的组会，连同议程、行动项和附件？`, '删除组会', { type: 'warning' })
  } catch {
    return
  }
  try {
    await meetingsApi.remove(meeting.value!.id)
    ElMessage.success('已删除')
    markSaved() // deleted: nothing left to lose
    closeTab(route.path)
    router.replace({ name: 'meetings' })
  } catch (e) {
    showActionError(e)
  }
}

// New meeting: copy the open items of the latest meeting. On save those old items are marked as carried over here.
const carrying = ref(false)
async function carryOver() {
  carrying.value = true
  try {
    const last = (await meetingsApi.list({ page_size: 1, before: form.date })).results[0]
    const taken = new Set(form.actions.map((r) => r.carried_from))
    const open = (last?.actions ?? []).filter((a) => !a.done_at && !taken.has(a.id))
    form.actions.push(...open.map((a) => ({ person: a.owner.id, text: a.content, due_date: a.due_date, carried_from: a.id })))
    if (!open.length) ElMessage.info(last ? `${last.date} 的组会没有未完成的行动项` : `${form.date} 之前没有组会`)
  } catch (e) {
    showError(e)
  } finally {
    carrying.value = false
  }
}

const isNew = !route.params.id
const loading = ref(false)
async function load() {
  if (isNew) return startEdit() // /meetings/new
  loading.value = true
  try {
    meeting.value = await meetingsApi.get(Number(route.params.id))
  } catch (e) {
    loadError.value = errorMessage(e)
  } finally {
    loading.value = false
  }
}
load()

// ---- read view ----
const presenting = computed(() => !!meeting.value?.agenda.some((a) => a.presenter.id === auth.user?.id))
const canToggle = (a: ActionItem) => a.owner.id === auth.user?.id || auth.isSupervisor

async function toggle(a: ActionItem, done: boolean) {
  try {
    Object.assign(a, await meetingsApi.setDone(a.id, done))
  } catch (e) {
    if (e instanceof ApiError && e.status === 403) ElMessage.error('只有负责人、导师和管理员可以修改完成状态')
    else showError(e)
  }
}

async function reload() {
  meeting.value = await meetingsApi.get(meeting.value!.id)
}
</script>

<template>
  <el-result v-if="loadError" icon="warning" :title="loadError">
    <template #extra><el-button @click="router.push({ name: 'meetings' })">返回组会列表</el-button></template>
  </el-result>
  <template v-else>
    <el-card v-loading="loading" class="card">
      <template #header>
        <PageHeader :back="{ name: 'meetings' }" :title="meeting ? `${meeting.date} ${meeting.title}` : isNew ? '新建组会' : ''">
          <template v-if="editing">
            <el-button v-if="meeting && auth.isManager" type="danger" plain @click="remove">删除组会</el-button>
            <el-button @click="meeting ? (editing = false) : router.push({ name: 'meetings' })">取消</el-button>
            <el-button type="primary" :loading="saving" @click="save">保存</el-button>
          </template>
          <template v-else-if="meeting">
            <IconButton :icon="Clock" label="修改历史" @click="historyOpen = true" />
            <el-button v-if="canEdit" type="primary" @click="startEdit">{{ auth.isSupervisor ? '编辑' : '记录纪要' }}</el-button>
          </template>
        </PageHeader>
      </template>
      <el-form v-if="editing" class="form-page" label-position="top" @submit.prevent="save">
        <div v-if="auth.isSupervisor" class="form-grid">
          <el-form-item label="日期" :error="errors.fe('date')" required>
            <el-date-picker v-model="form.date" type="date" value-format="YYYY-MM-DD" :clearable="false" />
          </el-form-item>
          <el-form-item label="时间" :error="errors.fe('time')">
            <el-time-select v-model="form.time" start="07:00" step="00:15" end="22:00" placeholder="如 19:00" />
          </el-form-item>
          <el-form-item class="span-2" label="标题" :error="errors.fe('title')"><el-input v-model="form.title" /></el-form-item>
          <el-form-item class="span-2" label="地点 / 会议号" :error="errors.fe('location')">
            <el-input v-model="form.location" placeholder="会议室，或线上会议号" />
          </el-form-item>
          <el-form-item label="记录人" :error="errors.fe('recorder_id')">
            <el-select v-model="form.recorder" filterable clearable placeholder="本组成员">
              <el-option v-for="m in memberOptions" :key="m.id" :label="m.name" :value="m.id" />
            </el-select>
          </el-form-item>
        </div>

        <el-form-item v-if="auth.isSupervisor" label="议程" :error="errors.fe('agenda')">
          <div class="rows">
            <div v-for="(r, i) in form.agenda" :key="i" class="row">
              <el-select v-model="r.person" filterable placeholder="汇报人" aria-label="汇报人" class="person">
                <el-option v-for="m in memberOptions" :key="m.id" :label="m.name" :value="m.id" />
              </el-select>
              <el-input v-model="r.text" placeholder="汇报内容" aria-label="汇报内容" class="text" />
              <el-button :icon="Delete" text aria-label="删除这一项" @click="form.agenda.splice(i, 1)" />
            </div>
            <el-button :icon="Plus" text @click="form.agenda.push({ person: null, text: '', due_date: null })">添加汇报</el-button>
          </div>
        </el-form-item>

        <el-form-item label="纪要" :error="errors.fe('minutes')">
          <el-input v-model="form.minutes" type="textarea" :autosize="{ minRows: 4, maxRows: 16 }" placeholder="讨论内容和结论" />
        </el-form-item>

        <el-form-item label="行动项" :error="errors.fe('actions')">
          <div class="rows">
            <div v-for="(r, i) in form.actions" :key="r.id ?? `new-${i}`" class="row">
              <el-select v-model="r.person" filterable placeholder="负责人" aria-label="负责人" class="person">
                <el-option v-for="m in memberOptions" :key="m.id" :label="m.name" :value="m.id" />
              </el-select>
              <el-input v-model="r.text" placeholder="事项" aria-label="事项" class="text" />
              <el-date-picker v-model="r.due_date" type="date" value-format="YYYY-MM-DD" placeholder="截止日期" aria-label="截止日期" class="due" />
              <el-button :icon="Delete" text aria-label="删除这一项" @click="form.actions.splice(i, 1)" />
            </div>
            <div class="row">
              <el-button :icon="Plus" text @click="form.actions.push({ person: null, text: '', due_date: null })">添加行动项</el-button>
              <el-button v-if="!meeting" text :loading="carrying" @click="carryOver">带入上次未完成的事项</el-button>
            </div>
          </div>
        </el-form-item>
        <el-alert v-for="msg in errors.others.value" :key="msg" :title="msg" type="error" :closable="false" />
      </el-form>
      <template v-else-if="meeting">
        <p v-if="meeting.time || meeting.location || meeting.recorder" class="when">
          <span v-if="meeting.time">{{ meeting.time }}</span>
          <span v-if="meeting.location">{{ meeting.location }}</span>
          <span v-if="meeting.recorder">记录人：{{ meeting.recorder.name }}</span>
        </p>
        <div class="section-title">议程</div>
        <ol v-if="meeting.agenda.length" class="agenda">
          <li v-for="a in meeting.agenda" :key="a.id"><b>{{ a.presenter.name }}</b>：{{ a.topic }}</li>
        </ol>
        <p v-else class="muted">暂无议程</p>
      </template>
    </el-card>

    <template v-if="meeting && !editing">
      <el-card class="card" header="纪要">
        <p v-if="meeting.minutes" class="pre">{{ meeting.minutes }}</p>
        <p v-else class="muted">暂无纪要</p>
      </el-card>
      <el-card class="card" header="行动项">
        <el-table :data="meeting.actions" empty-text="暂无行动项">
          <el-table-column prop="content" label="事项" min-width="220" />
          <el-table-column label="负责人" min-width="90">
            <template #default="{ row }">{{ row.owner.name }}</template>
          </el-table-column>
          <el-table-column label="完成" min-width="70">
            <template #default="{ row }">
              <RouterLink v-if="row.carried_to" :to="{ name: 'meeting-detail', params: { id: row.carried_to.id } }">已转入 {{ row.carried_to.date }} 组会</RouterLink>
              <el-checkbox
                v-else
                :model-value="!!row.done_at"
                :disabled="!canToggle(row as ActionItem)"
                :aria-label="`完成：${row.content}`"
                @change="(v) => toggle(row as ActionItem, !!v)"
              />
            </template>
          </el-table-column>
          <el-table-column label="截止" min-width="110">
            <template #default="{ row }">
              <span :class="{ overdue: overdue(row as ActionItem) }">{{ row.due_date ?? '' }}{{ overdue(row as ActionItem) ? '（已过期）' : '' }}</span>
            </template>
          </el-table-column>
          <el-table-column label="完成时间" min-width="140">
            <template #default="{ row }">{{ row.done_at ? formatTime(row.done_at) : '' }}</template>
          </el-table-column>
        </el-table>
      </el-card>
      <el-card class="card" header="附件">
        <AttachmentList
          :attachments="meeting.files"
          :with-kinds="false"
          accept=""
          hint="汇报 PPT 等，任意类型，单个不超过 2 GB"
          :upload="presenting || auth.isSupervisor ? (file, _kind, onProgress) => meetingsApi.upload(meeting!.id, file, onProgress) : undefined"
          :can-delete="(f) => f.uploaded_by.id === auth.user?.id || auth.isSupervisor"
          :remove="meetingsApi.removeFile"
          @changed="reload"
        />
      </el-card>
      <HistoryDrawer
        v-model="historyOpen"
        :load="() => meetingsApi.history(meeting!.id)"
        :labels="{ title: '标题', time: '时间', location: '地点 / 会议号', recorder: '记录人' }"
      />
    </template>
  </template>
</template>

<style scoped>
.when {
  display: flex;
  flex-wrap: wrap;
  gap: 4px 16px;
  margin: 0 0 12px;
  color: var(--lab-text-2);
}
.section-title {
  margin-bottom: 8px;
  font-weight: 600;
}
.grow {
  flex: 1;
}
.rows {
  display: flex;
  flex-direction: column;
  gap: 8px;
  width: 100%;
}
.row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.person {
  width: 130px;
}
.text {
  flex: 1;
  min-width: 200px;
}
.due {
  width: 150px;
}
.agenda {
  margin: 0;
  padding-left: 20px;
  line-height: 1.9;
}
.pre {
  margin: 0;
  white-space: pre-wrap;
}
.muted {
  margin: 0;
  color: var(--lab-text-3);
}
.overdue {
  color: var(--el-color-danger);
}
</style>

<script setup lang="ts">
import { replaceSavedEditor } from '@/router/saved-editor'
import { computed, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Delete, Plus } from '@element-plus/icons-vue'
import { meetingsApi } from '@/modules/meetings/api'
import { membersApi } from '@/modules/members/api'
import { ApiError } from '@/api/client'
import type { ActionItem, Meeting, MeetingWrite } from '@/api/types'
import { useOptions } from '@/composables/useOptions'
import { useAuthStore } from '@/stores/auth'
import { formatTime, mergeById, toDateStr } from '@/utils/format'
import { isNotFound, showActionError, showError, useFieldErrors } from '@/utils/errors'
import AttachmentList from '@/components/AttachmentList.vue'
import HistoryDrawer from '@/components/HistoryDrawer.vue'
import PageHeader from '@/components/PageHeader.vue'

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
  mergeById(members.value, [...(meeting.value?.agenda.map((a) => a.presenter) ?? []), ...(meeting.value?.actions.map((a) => a.owner) ?? [])]),
)
const today = toDateStr(new Date())
const overdue = (a: ActionItem) => !a.done_at && !!a.due_date && a.due_date < today

// ---- edit form (managers) ----
interface Row {
  id?: number
  person: number | null
  text: string
  due_date: string | null
}
const form = reactive({ date: today, title: '组会', minutes: '', agenda: [] as Row[], actions: [] as Row[] })
const errors = useFieldErrors(['date', 'title', 'minutes', 'agenda', 'actions'])

function startEdit() {
  const m = meeting.value
  Object.assign(form, {
    date: m?.date ?? today,
    title: m?.title ?? '组会',
    minutes: m?.minutes ?? '',
    agenda: m ? m.agenda.map((a) => ({ person: a.presenter.id, text: a.topic, due_date: null })) : [{ person: null, text: '', due_date: null }],
    actions: m ? m.actions.map((a) => ({ id: a.id, person: a.owner.id, text: a.content, due_date: a.due_date })) : [],
  })
  errors.clear()
  editing.value = true
}

function body(): MeetingWrite {
  const filled = (r: Row) => r.person !== null || r.text.trim() // an untouched blank row is not sent
  return {
    date: form.date,
    title: form.title,
    minutes: form.minutes,
    agenda: form.agenda.filter(filled).map((r) => ({ presenter_id: r.person!, topic: r.text })),
    actions: form.actions.filter(filled).map((r) => ({ id: r.id, owner_id: r.person!, content: r.text, due_date: r.due_date || null })),
  }
}

async function save() {
  saving.value = true
  try {
    const source = router.currentRoute?.value
    const saved = meeting.value ? await meetingsApi.update(meeting.value.id, body()) : await meetingsApi.create(body())
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
    router.replace({ name: 'meetings' })
  } catch (e) {
    showActionError(e)
  }
}

async function load() {
  const id = Number(route.params.id)
  if (!id) return startEdit() // /meetings/new
  try {
    meeting.value = await meetingsApi.get(id)
  } catch (e) {
    if (isNotFound(e)) loadError.value = '记录不存在或无权查看'
    else showError(e)
  }
}
load()

// ---- read view ----
const presenting = computed(() => !!meeting.value?.agenda.some((a) => a.presenter.id === auth.user?.id))
const canToggle = (a: ActionItem) => a.owner.id === auth.user?.id || auth.isManager

async function toggle(a: ActionItem, done: boolean) {
  try {
    Object.assign(a, await meetingsApi.setDone(a.id, done))
  } catch (e) {
    if (e instanceof ApiError && e.status === 403) ElMessage.error('只有负责人和管理员可以修改完成状态')
    else showError(e)
  }
}

async function reload() {
  meeting.value = await meetingsApi.get(meeting.value!.id)
}
</script>

<template>
  <div v-if="loadError" class="card"><el-empty :description="loadError" /></div>
  <template v-else>
    <el-card class="card">
      <template #header>
        <PageHeader :back="{ name: 'meetings' }" :title="meeting ? `${meeting.date} ${meeting.title}` : '新建组会'">
          <template v-if="editing">
            <el-button v-if="meeting" type="danger" plain @click="remove">删除组会</el-button>
            <el-button @click="meeting ? (editing = false) : router.push({ name: 'meetings' })">取消</el-button>
            <el-button type="primary" :loading="saving" @click="save">保存</el-button>
          </template>
          <template v-else-if="meeting">
            <el-button @click="historyOpen = true">修改历史</el-button>
            <el-button v-if="auth.isManager" type="primary" @click="startEdit">编辑</el-button>
          </template>
        </PageHeader>
      </template>
      <el-form v-if="editing" class="form-page" label-position="top" @submit.prevent="save">
        <div class="form-grid">
          <el-form-item label="日期" :error="errors.fe('date')" required>
            <el-date-picker v-model="form.date" type="date" value-format="YYYY-MM-DD" :clearable="false" />
          </el-form-item>
          <el-form-item class="span-2" label="标题" :error="errors.fe('title')"><el-input v-model="form.title" /></el-form-item>
        </div>

        <el-form-item label="议程" :error="errors.fe('agenda')">
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
            <el-button :icon="Plus" text @click="form.actions.push({ person: null, text: '', due_date: null })">添加行动项</el-button>
          </div>
        </el-form-item>
        <el-alert v-for="msg in errors.others.value" :key="msg" :title="msg" type="error" :closable="false" />
      </el-form>
      <template v-else-if="meeting">
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
          <el-table-column label="完成" width="70">
            <template #default="{ row }">
              <el-checkbox
                :model-value="!!row.done_at"
                :disabled="!canToggle(row as ActionItem)"
                :aria-label="`完成：${row.content}`"
                @change="(v) => toggle(row as ActionItem, !!v)"
              />
            </template>
          </el-table-column>
          <el-table-column label="负责人" min-width="90">
            <template #default="{ row }">{{ row.owner.name }}</template>
          </el-table-column>
          <el-table-column prop="content" label="事项" min-width="220" />
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
          :upload="presenting || auth.isManager ? (file) => meetingsApi.upload(meeting!.id, file) : undefined"
          :can-delete="(f) => f.uploaded_by.id === auth.user?.id || auth.isManager"
          :remove="meetingsApi.removeFile"
          @changed="reload"
        />
      </el-card>
      <HistoryDrawer v-model="historyOpen" :load="() => meetingsApi.history(meeting!.id)" :labels="{ title: '标题' }" />
    </template>
  </template>
</template>

<style scoped>
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

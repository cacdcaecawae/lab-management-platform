<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import FullCalendar from '@fullcalendar/vue3'
import timeGridPlugin from '@fullcalendar/timegrid'
import interactionPlugin from '@fullcalendar/interaction'
import zhCnLocale from '@fullcalendar/core/locales/zh-cn'
import type { CalendarOptions, EventInput, EventSourceFuncArg } from '@fullcalendar/core'
import { bookingsApi, equipmentApi } from '../api'
import { projectsApi } from '@/api/projects'
import type { Booking, Condition } from '@/api/types'
import { useOptions } from '@/composables/useOptions'
import { useAuthStore } from '@/stores/auth'
import { BOOKING_KIND_LABELS, CONDITION_LABELS, STATUS, formatPeriod } from '@/utils/format'
import { showError, useFieldErrors } from '@/utils/errors'
import BookingFormDialog from '../components/BookingFormDialog.vue'

const auth = useAuthStore()
const route = useRoute()
const router = useRouter()
const calendar = ref<InstanceType<typeof FullCalendar>>()
const equipment = useOptions(() => equipmentApi.list({ page_size: 100 }))
const projects = useOptions(() => projectsApi.list({ status: 'active', page_size: 100 }))

const filters = reactive({
  equipment: route.query.equipment ? Number(route.query.equipment) : ('' as number | ''),
  mine: '' as 1 | '',
})
const picked = computed(() => equipment.value.find((e) => e.id === filters.equipment))
watch(filters, () => {
  router.replace({ query: filters.equipment ? { equipment: filters.equipment } : {} }) // also drops ?booking
  calendar.value?.getApi().refetchEvents()
})

// The API accepts a start up to 5 minutes in the past (form-filling time); the calendar only offers future slots.
const GRACE_MS = 5 * 60_000
const narrow = window.matchMedia('(max-width: 768px)').matches

async function fetchEvents(info: EventSourceFuncArg): Promise<EventInput[]> {
  try {
    const list = await bookingsApi.list({ from: info.start.toISOString(), to: info.end.toISOString(), ...filters })
    return list.map((b) => ({
      id: String(b.id),
      title: `${b.equipment.code} ${b.kind === 'maintenance' ? '维护' : b.user.name}`,
      start: b.start_at,
      end: b.end_at,
      classNames: [b.kind === 'maintenance' ? 'ev-maint' : b.user.id === auth.user?.id ? 'ev-mine' : 'ev-other'],
      extendedProps: { booking: b },
    }))
  } catch (e) {
    showError(e)
    return []
  }
}

const options: CalendarOptions = {
  plugins: [timeGridPlugin, interactionPlugin],
  locale: zhCnLocale,
  initialView: narrow ? 'timeGridDay' : 'timeGridWeek',
  headerToolbar: { left: 'prev,next today', center: 'title', right: narrow ? '' : 'timeGridWeek,timeGridDay' },
  // zh-cn names the arrows 上月 / 下月 even in week and day views; $0 is the current view's unit (周 / 日).
  buttonHints: { prev: '上一$0', next: '下一$0' },
  firstDay: 1,
  allDaySlot: false,
  slotDuration: '00:30:00',
  scrollTime: '08:00:00',
  contentHeight: 620,
  nowIndicator: true,
  selectable: true,
  selectMirror: true,
  selectAllow: (span) => span.start.getTime() >= Date.now() - GRACE_MS,
  select: (info) => openCreate(info.start, info.end),
  eventClick: (info) => (detail.value = info.event.extendedProps.booking as Booking),
  events: fetchEvents,
  slotLabelFormat: { hour: '2-digit', minute: '2-digit', hour12: false },
  eventTimeFormat: { hour: '2-digit', minute: '2-digit', hour12: false },
}

// ---- new booking ----
const creating = ref(false)
const initial = ref({ equipmentId: null as number | null, start: null as Date | null, end: null as Date | null })
function openCreate(start: Date | null = null, end: Date | null = null) {
  initial.value = { equipmentId: filters.equipment || null, start, end }
  creating.value = true
}
function onSaved() {
  ElMessage.success('预约成功')
  calendar.value?.getApi().unselect()
  calendar.value?.getApi().refetchEvents()
}

// ---- booking detail: cancel / usage report ----
const detail = ref<Booking | null>(null)
const detailOpen = computed({ get: () => !!detail.value, set: (v) => !v && (detail.value = null) })
const mine = computed(() => detail.value?.user.id === auth.user?.id)
const started = computed(() => !!detail.value && new Date(detail.value.start_at).getTime() <= Date.now())
const canCancel = computed(() => !!detail.value && !detail.value.report && (auth.isManager || (mine.value && !started.value)))
const canReport = computed(() => !!detail.value && mine.value && detail.value.kind === 'use' && started.value && !detail.value.report)

const reportForm = reactive({ condition: 'normal' as Condition, description: '', photo: null as File | null })
const reportErrors = useFieldErrors(['condition', 'description', 'photo'])
const busy = ref(false)
watch(detail, () => {
  Object.assign(reportForm, { condition: 'normal', description: '', photo: null })
  reportErrors.clear()
})
// Links from the workbench: /bookings?booking=<id> opens that booking on its week.
if (route.query.booking) {
  bookingsApi.get(Number(route.query.booking)).then((b) => {
    detail.value = b
    calendar.value?.getApi().gotoDate(b.start_at)
  }, showError)
}

const pickPhoto = (e: Event) => (reportForm.photo = (e.target as HTMLInputElement).files?.[0] ?? null)

async function cancel() {
  const b = detail.value
  if (!b) return
  try {
    await ElMessageBox.confirm(`取消 ${b.equipment.code} ${formatPeriod(b.start_at, b.end_at)} 的预约？`, '取消预约', {
      confirmButtonText: '取消预约',
      cancelButtonText: '不取消',
      type: 'warning',
    })
  } catch {
    return
  }
  busy.value = true
  try {
    await bookingsApi.cancel(b.id)
    ElMessage.success('预约已取消')
    detail.value = null
    calendar.value?.getApi().refetchEvents()
  } catch (e) {
    showError(e)
  } finally {
    busy.value = false
  }
}

async function submitReport() {
  const b = detail.value
  if (!b) return
  busy.value = true
  try {
    detail.value = await bookingsApi.report(b.id, reportForm)
    ElMessage.success(reportForm.condition === 'abnormal' ? '已登记异常，设备转为待检查，管理员会收到提醒' : '已登记')
    calendar.value?.getApi().refetchEvents()
  } catch (e) {
    reportErrors.handle(e)
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <el-card class="card">
    <div class="page-toolbar">
      <el-select v-model="filters.equipment" aria-label="设备" filterable clearable placeholder="全部设备">
        <el-option v-for="e in equipment" :key="e.id" :label="`${e.code} ${e.name}`" :value="e.id" />
      </el-select>
      <el-checkbox v-model="filters.mine" :true-value="1" false-value="">只看我的</el-checkbox>
      <span class="grow" />
      <el-button type="primary" @click="openCreate()">新建预约</el-button>
    </div>
    <el-alert
      v-if="picked && picked.status !== 'available'"
      :title="`${picked.code} 当前为“${STATUS[picked.status].label}”，暂不能预约使用`"
      type="warning"
      :closable="false"
      class="status-alert"
    />
    <FullCalendar ref="calendar" class="calendar" :options="options" />
  </el-card>

  <BookingFormDialog v-model="creating" :equipment="equipment" :projects="projects" :initial="initial" @saved="onSaved" />

  <el-dialog v-model="detailOpen" title="预约详情" width="min(520px, 95vw)">
    <template v-if="detail">
      <el-descriptions :column="1" border>
        <el-descriptions-item label="设备">
          <RouterLink :to="{ name: 'equipment-detail', params: { id: detail.equipment.id } }">
            <span class="code">{{ detail.equipment.code }}</span> {{ detail.equipment.name }}
          </RouterLink>
        </el-descriptions-item>
        <el-descriptions-item label="时间">{{ formatPeriod(detail.start_at, detail.end_at) }}</el-descriptions-item>
        <el-descriptions-item label="预约人">{{ detail.user.name }}</el-descriptions-item>
        <el-descriptions-item label="类型">{{ BOOKING_KIND_LABELS[detail.kind] }}</el-descriptions-item>
        <el-descriptions-item label="项目">{{ detail.project?.name }}</el-descriptions-item>
        <el-descriptions-item label="用途">{{ detail.purpose }}</el-descriptions-item>
        <el-descriptions-item v-if="detail.report" label="使用后状况">
          <div class="actions">
            <el-tag class="status-tag" :type="detail.report.condition === 'abnormal' ? 'danger' : 'success'" disable-transitions>
              {{ CONDITION_LABELS[detail.report.condition] }}
            </el-tag>
            <span>{{ detail.report.description }}</span>
            <a v-if="detail.report.photo_url" :href="detail.report.photo_url" target="_blank" rel="noopener">照片</a>
          </div>
        </el-descriptions-item>
      </el-descriptions>

      <el-form v-if="canReport" label-position="top" class="report-form" @submit.prevent="submitReport">
        <el-form-item label="登记使用结果" :error="reportErrors.fe('condition')">
          <el-radio-group v-model="reportForm.condition">
            <el-radio value="normal">正常</el-radio>
            <el-radio value="abnormal">异常</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="说明" :error="reportErrors.fe('description')" :required="reportForm.condition === 'abnormal'">
          <el-input v-model="reportForm.description" type="textarea" :autosize="{ minRows: 2 }" placeholder="异常时写明现象，例如 探头线接触不良" />
        </el-form-item>
        <el-form-item label="照片（可选，JPG / PNG / WebP，10 MB 以内）" :error="reportErrors.fe('photo')">
          <input type="file" accept="image/jpeg,image/png,image/webp" @change="pickPhoto" />
        </el-form-item>
        <el-alert v-for="msg in reportErrors.others.value" :key="msg" :title="msg" type="error" :closable="false" />
      </el-form>
    </template>
    <template #footer>
      <el-button v-if="canCancel" type="danger" plain :loading="busy" @click="cancel">取消预约</el-button>
      <el-button v-if="canReport" type="primary" :loading="busy" @click="submitReport">登记</el-button>
      <el-button @click="detailOpen = false">关闭</el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
.status-alert {
  margin-bottom: 12px;
}
.report-form {
  margin-top: 20px;
}
.calendar {
  --fc-border-color: var(--lab-border);
  --fc-today-bg-color: #fafafa;
  --fc-now-indicator-color: var(--el-color-danger);
  --fc-button-bg-color: #fff;
  --fc-button-text-color: var(--lab-text);
  --fc-button-border-color: #dcdcdc;
  --fc-button-hover-bg-color: var(--lab-bg-hover);
  --fc-button-hover-border-color: #dcdcdc;
  --fc-button-active-bg-color: var(--lab-bg-active);
  --fc-button-active-border-color: #cfcfcf;
  --fc-highlight-color: rgba(13, 13, 13, 0.06);
  font-size: 13px;
}
.calendar :deep(a) {
  color: inherit;
  text-decoration: none;
}
.calendar :deep(.fc-toolbar-title) {
  font-size: 16px;
  font-weight: 600;
}
.calendar :deep(.fc-button) {
  font-size: 13px;
  box-shadow: none !important;
}
.calendar :deep(.fc-event) {
  cursor: pointer;
  border-radius: 6px;
  padding: 1px 3px;
}
.calendar :deep(.ev-mine) {
  background: var(--lab-text);
  border-color: var(--lab-text);
  color: #fff;
}
.calendar :deep(.ev-other) {
  background: #e9e9e9;
  border-color: #d6d6d6;
}
.calendar :deep(.ev-other .fc-event-main) {
  color: var(--lab-text);
}
.calendar :deep(.ev-maint) {
  background: repeating-linear-gradient(135deg, #fff4e5, #fff4e5 6px, #ffe9cc 6px, #ffe9cc 12px);
  border-color: #f0c78a;
}
.calendar :deep(.ev-maint .fc-event-main) {
  color: #7a4a06;
}
</style>

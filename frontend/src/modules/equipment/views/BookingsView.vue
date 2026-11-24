<script setup lang="ts">
import { computed, nextTick, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import FullCalendar from '@fullcalendar/vue3'
import dayGridPlugin from '@fullcalendar/daygrid'
import timeGridPlugin from '@fullcalendar/timegrid'
import interactionPlugin from '@fullcalendar/interaction'
import zhCnLocale from '@fullcalendar/core/locales/zh-cn'
import type { CalendarOptions, DatesSetArg, EventInput, EventSourceFuncArg } from '@fullcalendar/core'
import { ArrowLeft, ArrowRight } from '@element-plus/icons-vue'
import { bookingsApi, equipmentApi } from '../api'
import { projectsApi } from '@/modules/projects/api'
import type { Booking, Condition } from '@/api/types'
import { useOptions } from '@/composables/useOptions'
import { useAuthStore } from '@/stores/auth'
import { BOOKING_KIND_LABELS, CONDITION_LABELS, STATUS, formatPeriod, formatTime } from '@/utils/format'
import { showError, useFieldErrors } from '@/utils/errors'
import BookingFormDialog from '../components/BookingFormDialog.vue'
import BookingList from '../components/BookingList.vue'
import FormDialog from '@/components/FormDialog.vue'
import PageToolbar from '@/components/PageToolbar.vue'
import PhotoPicker from '@/components/PhotoPicker.vue'

const auth = useAuthStore()
const route = useRoute()
const router = useRouter()
const calendar = ref<InstanceType<typeof FullCalendar>>()
const equipment = useOptions(() => equipmentApi.list({ page_size: 100 }))
const projects = useOptions(() => projectsApi.list({ status: 'active', page_size: 100 }))

// Each device keeps one colour (by its place in the list). Its bookings use it: solid for one's own, tinted for others.
const PALETTE = ['#0071e3', '#1f7a35', '#a34a00', '#7a3fbf', '#00796b', '#b0336b', '#3f51b5', '#795548']
const colorOf = (id: number) => PALETTE[Math.max(0, equipment.value.findIndex((e) => e.id === id)) % PALETTE.length]
const tint = (hex: string) => {
  const n = parseInt(hex.slice(1), 16)
  const mix = (c: number) => Math.round(c * 0.14 + 255 * 0.86)
  return `rgb(${mix(n >> 16)}, ${mix((n >> 8) & 255)}, ${mix(n & 255)})`
}

// Devices ticked in the side list: all of them, or only the one the equipment page linked to (?equipment=).
const linked = route.query.equipment ? Number(route.query.equipment) : null
const shown = ref<number[]>([])
watch(equipment, (list) => (shown.value = list.some((e) => e.id === linked) ? [linked as number] : list.map((e) => e.id)), {
  once: true,
})
// Phones: the page opens on the working day, 08:00 at the top (the night and the device list are above it); once,
// after the device list has its height.
if (window.matchMedia('(max-width: 768px)').matches) {
  watch(equipment, () => nextTick(() => document.querySelector('.calendar .fc-timegrid-slot[data-time="08:00:00"]')?.scrollIntoView({ block: 'start' })), {
    once: true,
  })
}
const allShown = computed(() => equipment.value.length > 0 && shown.value.length === equipment.value.length)
const toggleAll = (on: boolean | string | number) => (shown.value = on ? equipment.value.map((e) => e.id) : [])
const mineOnly = ref<1 | ''>('')
const only = computed(() => (shown.value.length === 1 ? equipment.value.find((e) => e.id === shown.value[0]) : undefined))
watch([shown, mineOnly], () => {
  router.replace({ query: only.value ? { equipment: only.value.id } : {} }) // also drops ?booking
  api()?.refetchEvents()
})

// The API accepts a start up to 5 minutes in the past (form-filling time); the calendar only offers future slots.
const GRACE_MS = 5 * 60_000
const narrow = window.matchMedia('(max-width: 768px)').matches

async function fetchEvents(info: EventSourceFuncArg): Promise<EventInput[]> {
  try {
    const query = { from: info.start.toISOString(), to: info.end.toISOString(), equipment: only.value?.id ?? ('' as const), mine: mineOnly.value }
    const list = await bookingsApi.list(query)
    const hidden = new Set(equipment.value.map((e) => e.id).filter((id) => !shown.value.includes(id)))
    return list
      .filter((b) => !hidden.has(b.equipment.id))
      .map((b) => {
        const color = colorOf(b.equipment.id)
        const own = b.user.id === auth.user?.id
        const maint = b.kind === 'maintenance'
        return {
          id: String(b.id),
          title: `${b.equipment.code} ${maint ? '维护' : b.user.name}`,
          start: b.start_at,
          end: b.end_at,
          classNames: [maint ? 'ev-maint' : own ? 'ev-mine' : 'ev-other'],
          backgroundColor: maint ? undefined : own ? color : tint(color),
          borderColor: color,
          textColor: maint ? undefined : own ? '#fff' : '#1d1d1f',
          extendedProps: { booking: b },
        }
      })
  } catch (e) {
    showError(e)
    return []
  }
}

// The calendar's own header is off: the page toolbar drives it, and the side panel's month jumps to a date.
const VIEWS = { dayGridMonth: '月', timeGridWeek: '周', timeGridDay: '日' } as const
const UNIT: Record<string, string> = { dayGridMonth: '月', timeGridWeek: '周', timeGridDay: '天' }
const WEEKDAYS = ['周日', '周一', '周二', '周三', '周四', '周五', '周六']
const view = ref<string>(narrow ? 'timeGridDay' : 'timeGridWeek')
// 列表 (also ?view=list from the workbench) hides the calendar but keeps it, so switching back keeps its week.
const listing = ref(route.query.view === 'list')
const list = ref<InstanceType<typeof BookingList>>()
const refresh = () => (listing.value ? list.value?.load() : api()?.refetchEvents())
function switchView(v: string) {
  listing.value = v === 'list'
  if (!listing.value) void nextTick(() => api()?.changeView(v))
}
const title = ref('')
const day = ref(new Date())
const api = () => calendar.value?.getApi()
function onDatesSet(info: DatesSetArg) {
  title.value = info.view.title
  view.value = info.view.type
  day.value = info.view.calendar.getDate()
}
const jump = (d: unknown) => d instanceof Date && api()?.gotoDate(d)

const options: CalendarOptions = {
  plugins: [dayGridPlugin, timeGridPlugin, interactionPlugin],
  locale: zhCnLocale,
  initialView: view.value,
  headerToolbar: false,
  firstDay: 1,
  height: 'auto', // the whole day on the page, no scroll box inside the card
  allDaySlot: false,
  slotDuration: '01:00:00',
  snapDuration: '00:30:00',
  nowIndicator: true,
  navLinks: true, // a day number or column header opens that day
  navLinkDayClick: 'timeGridDay',
  selectable: true,
  selectMirror: true,
  selectAllow: (span) => span.start.getTime() >= Date.now() - GRACE_MS,
  select: (info) => openCreate(info.start, info.end),
  eventClick: (info) => (detail.value = info.event.extendedProps.booking as Booking),
  events: fetchEvents,
  datesSet: onDatesSet,
  slotLabelFormat: { hour: '2-digit', minute: '2-digit', hour12: false },
  eventTimeFormat: { hour: '2-digit', minute: '2-digit', hour12: false },
  eventDisplay: 'block', // coloured bars in the month view too, not dots
  views: {
    dayGridMonth: { selectable: false, dayMaxEvents: 3, dayHeaderFormat: { weekday: 'short' } },
    timeGrid: {
      dayHeaderContent: (arg) => ({
        html: `<span class="dow">${WEEKDAYS[arg.date.getDay()]}</span><span class="dom">${arg.date.getMonth() + 1}/${arg.date.getDate()}</span>`,
      }),
    },
  },
}

// ---- new booking ----
const creating = ref(false)
const initial = ref({ equipmentId: null as number | null, start: null as Date | null, end: null as Date | null })
function openCreate(start: Date | null = null, end: Date | null = null) {
  initial.value = { equipmentId: only.value?.id ?? null, start, end }
  creating.value = true
}
function onSaved() {
  ElMessage.success('预约成功')
  api()?.unselect()
  api()?.refetchEvents()
}

// ---- booking detail: cancel / usage report ----
const detail = ref<Booking | null>(null)
const detailOpen = computed({ get: () => !!detail.value, set: (v) => !v && (detail.value = null) })
const mine = computed(() => detail.value?.user.id === auth.user?.id)
const started = computed(() => !!detail.value && new Date(detail.value.start_at).getTime() <= Date.now())
const canCancel = computed(() => !!detail.value && !detail.value.report && (auth.isManager || (mine.value && !started.value)))
const canReport = computed(() => !!detail.value && mine.value && detail.value.kind === 'use' && started.value && !detail.value.report)
// Under way (started, not over): the booker or a manager can end it now and free the rest of the time.
const canEnd = computed(() => {
  const b = detail.value
  return !!b && b.kind === 'use' && !b.planned_end_at && started.value && new Date(b.end_at).getTime() > Date.now() && (mine.value || auth.isManager)
})

const reportForm = reactive({ condition: 'normal' as Condition, description: '', photo: null as File | null })
const reportErrors = useFieldErrors(['condition', 'description', 'photo'])
const reportPhotoBusy = ref(false)
const busy = ref(false)
watch(detail, (b) => {
  reportPhotoBusy.value = false
  Object.assign(reportForm, { condition: 'normal', description: '', photo: null })
  reportErrors.clear()
  if (!b && route.query.booking) {
    // closed: the same link opens it again
    const { booking: _, ...query } = route.query
    void router.replace({ query })
  }
})
// Links from the workbench and notices: /bookings?booking=<id> opens that booking on its week, also when this page is
// already open (the view is reused).
watch(
  () => route.query.booking,
  (id) => {
    if (typeof id !== 'string' || !id) return
    bookingsApi.get(Number(id)).then((b) => {
      detail.value = b
      api()?.gotoDate(b.start_at)
    }, showError)
  },
  { immediate: true },
)

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
    refresh()
  } catch (e) {
    showError(e)
  } finally {
    busy.value = false
  }
}

async function endNow() {
  const b = detail.value
  if (!b) return
  try {
    await ElMessageBox.confirm(`现在结束 ${b.equipment.code} 的这次使用？之后的时间别人可以预约。`, '提前结束', {
      confirmButtonText: '提前结束',
      cancelButtonText: '不结束',
      type: 'warning',
    })
  } catch {
    return
  }
  busy.value = true
  try {
    detail.value = await bookingsApi.endNow(b.id)
    ElMessage.success('已提前结束，之后的时间已经空出来')
    refresh()
  } catch (e) {
    showError(e)
  } finally {
    busy.value = false
  }
}

async function submitReport() {
  const b = detail.value
  if (!b || reportPhotoBusy.value) return
  busy.value = true
  try {
    detail.value = await bookingsApi.report(b.id, { ...reportForm })
    ElMessage.success(reportForm.condition === 'abnormal' ? '已登记异常，设备转为待检查，管理员会收到提醒' : '已登记')
    refresh()
  } catch (e) {
    reportErrors.handle(e)
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <div class="booking-page">
    <el-card class="card main">
      <PageToolbar>
        <template v-if="!listing">
        <el-button-group>
          <el-button :icon="ArrowLeft" :aria-label="`上一${UNIT[view]}`" @click="api()?.prev()" />
          <el-button :icon="ArrowRight" :aria-label="`下一${UNIT[view]}`" @click="api()?.next()" />
        </el-button-group>
        <el-button @click="api()?.today()">今天</el-button>
        <span class="cal-title">{{ title }}</span>
        </template>
        <!-- stays in the card on a phone (the top bar only fits 新建预约); right-aligned on desktop beside it -->
        <el-radio-group class="view-switch" :model-value="listing ? 'list' : view" aria-label="视图" @change="(v) => switchView(String(v))">
          <el-radio-button v-for="(label, key) in VIEWS" :key="key" :value="key">{{ label }}</el-radio-button>
          <el-radio-button value="list">列表</el-radio-button>
        </el-radio-group>
        <template #actions>
          <el-button type="primary" @click="openCreate()">新建预约</el-button>
        </template>
      </PageToolbar>
      <el-alert
        v-if="only && only.status !== 'available'"
        :title="`${only.code} 当前为“${STATUS[only.status].label}”，暂不能预约使用`"
        type="warning"
        :closable="false"
        class="status-alert"
      />
      <BookingList v-if="listing" ref="list" :equipment="equipment" @open="(b) => (detail = b)" />
      <FullCalendar v-show="!listing" ref="calendar" class="calendar" :options="options" />
    </el-card>

    <el-card v-if="!listing" class="card side">
      <el-date-picker-panel class="mini" :model-value="day" :border="false" @update:model-value="jump" />
      <div class="side-head">
        <span>设备</span>
        <el-checkbox v-model="mineOnly" :true-value="1" false-value="">只看我的</el-checkbox>
      </div>
      <el-checkbox :model-value="allShown" :indeterminate="shown.length > 0 && !allShown" @change="toggleAll">全部设备</el-checkbox>
      <el-checkbox-group v-model="shown" class="devices" aria-label="显示哪些设备">
        <el-checkbox v-for="e in equipment" :key="e.id" :value="e.id">
          <span class="swatch" :style="{ background: colorOf(e.id) }" />
          <span class="code">{{ e.code }}</span> {{ e.name }}
          <span v-if="e.status !== 'available'" class="muted">· {{ STATUS[e.status].label }}</span>
        </el-checkbox>
      </el-checkbox-group>
      <p v-if="!equipment.length" class="muted">暂无设备</p>
    </el-card>
  </div>

  <BookingFormDialog v-model="creating" :equipment="equipment" :projects="projects" :initial="initial" @saved="onSaved" />

  <FormDialog
    v-model="detailOpen"
    title="预约详情"
    confirm-text="登记"
    cancel-text="关闭"
    :readonly="!canReport"
    :loading="busy"
    :disabled="reportPhotoBusy"
    @submit="submitReport"
  >
    <template #before>
      <el-descriptions v-if="detail" :column="1" border>
        <el-descriptions-item label="设备">
          <RouterLink :to="{ name: 'equipment-detail', params: { id: detail.equipment.id } }">
            <span class="code">{{ detail.equipment.code }}</span> {{ detail.equipment.name }}
          </RouterLink>
        </el-descriptions-item>
        <el-descriptions-item label="时间">
          {{ formatPeriod(detail.start_at, detail.end_at) }}
          <span v-if="detail.planned_end_at" class="muted">（提前结束，原定到 {{ formatTime(detail.planned_end_at).slice(11) }}）</span>
        </el-descriptions-item>
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
            <el-image
              v-if="detail.report.photo_url"
              class="report-thumb"
              :src="detail.report.photo_url"
              :preview-src-list="[detail.report.photo_url]"
              preview-teleported
              fit="cover"
              alt="使用照片"
            />
          </div>
        </el-descriptions-item>
      </el-descriptions>
    </template>
    <div v-if="canReport" class="report-form">
      <el-form-item label="登记使用结果" :error="reportErrors.fe('condition')">
        <el-radio-group v-model="reportForm.condition">
          <el-radio value="normal">正常</el-radio>
          <el-radio value="abnormal">异常</el-radio>
        </el-radio-group>
      </el-form-item>
      <el-form-item label="说明" :error="reportErrors.fe('description')" :required="reportForm.condition === 'abnormal'">
        <el-input v-model="reportForm.description" type="textarea" :autosize="{ minRows: 2 }" placeholder="异常时写明现象，例如 探头线接触不良" />
      </el-form-item>
      <el-form-item label="照片（可选，方便下一个人找设备）" :error="reportErrors.fe('photo')">
        <PhotoPicker v-if="detailOpen" v-model="reportForm.photo" v-model:processing="reportPhotoBusy" :disabled="busy" />
      </el-form-item>
      <el-alert v-for="msg in reportErrors.others.value" :key="msg" :title="msg" type="error" :closable="false" />
    </div>
    <template #extra>
      <el-button v-if="canEnd" :loading="busy" @click="endNow">提前结束</el-button>
      <el-button v-if="canCancel" type="danger" plain :loading="busy" @click="cancel">取消预约</el-button>
    </template>
  </FormDialog>
</template>

<style scoped>
.booking-page {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 300px;
  gap: 16px;
  align-items: start;
}
.booking-page > .card {
  margin-top: 0;
}
/* el-card and its body clip / scroll overflow, which would keep the calendar's day headers from sticking under the top bar */
.main,
.main :deep(.el-card__body) {
  overflow: visible;
}
.side {
  position: sticky;
  top: 68px;
}
.side :deep(.el-card__body) {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 12px 16px 16px;
}
/* Element Plus gives the month panel a fixed 322px; let it fit the side column */
.mini,
.mini :deep(.el-picker-panel__body-wrapper),
.mini :deep(.el-picker-panel__body),
.mini :deep(.el-picker-panel__content),
.mini :deep(.el-date-table) {
  width: 100%;
  min-width: 0;
  margin: 0;
}
.mini :deep(.el-date-table td) {
  width: auto;
}
.side-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding-top: 8px;
  border-top: 1px solid var(--lab-border);
  font-weight: 600;
}
.devices {
  display: flex;
  flex-direction: column;
}
.devices .el-checkbox {
  height: auto;
  min-height: 30px;
  margin-right: 0;
  white-space: normal;
}
/* a ticked device is a choice, not a link: keep its name black */
.side :deep(.el-checkbox__input.is-checked + .el-checkbox__label) {
  color: var(--lab-text);
}
.swatch {
  display: inline-block;
  width: 10px;
  height: 10px;
  margin-right: 6px;
  border-radius: 3px;
  vertical-align: -1px;
}
.cal-title {
  margin-left: 8px;
  font-size: 16px;
  font-weight: 600;
}
.view-switch {
  margin-left: auto;
}
@media (max-width: 768px) {
  .view-switch {
    margin-left: 0;
  }
  /* the devices above the calendar, not after its 24 hours; jumping to a date is the 月 view's */
  .side {
    order: -1;
  }
  .mini {
    display: none;
  }
  .side-head {
    padding-top: 0;
    border-top: 0;
  }
  /* scrolled to 08:00 (script): stop under the top bar (52px) and the sticky day header (53px) */
  .calendar :deep(.fc-timegrid-slot) {
    scroll-margin-top: 106px;
  }
}
.status-alert {
  margin-bottom: 12px;
}
.report-form {
  margin-top: 20px;
}
.calendar {
  --fc-border-color: var(--lab-border);
  --fc-today-bg-color: var(--el-color-primary-light-9);
  --fc-now-indicator-color: var(--el-color-danger);
  --fc-highlight-color: rgba(0, 113, 227, 0.08);
  --fc-neutral-bg-color: var(--lab-bg-subtle);
  --fc-page-bg-color: var(--lab-bg-card);
  font-size: 13px;
}
.calendar :deep(a) {
  color: inherit;
  text-decoration: none;
}
.calendar :deep(.fc-col-header-cell) {
  padding: 6px 0;
  font-weight: 500;
  color: var(--lab-text-2);
}
.calendar :deep(.dow),
.calendar :deep(.dom) {
  display: block;
  line-height: 1.3;
}
.calendar :deep(.dom) {
  font-size: 15px;
  font-weight: 600;
  color: var(--lab-text);
}
.calendar :deep(.fc-day-today .dom) {
  color: var(--el-color-primary);
}
/* Headers stay visible under the top bar while the page scrolls. */
.calendar :deep(.fc-scrollgrid-section-header.fc-scrollgrid-section-sticky > *) {
  top: 52px;
}
.calendar :deep(.fc-timegrid-slot) {
  height: 32px;
}
.calendar :deep(.fc-timegrid-slot-label) {
  color: var(--lab-text-3);
  vertical-align: top;
}
.calendar :deep(.fc-daygrid-day-number) {
  padding: 6px 8px;
  color: var(--lab-text-2);
}
.calendar :deep(.fc-event) {
  cursor: pointer;
  border-radius: 6px;
  border-width: 0 0 0 3px;
  padding: 1px 4px;
}
.calendar :deep(.ev-mine) {
  border-width: 0;
}
.calendar :deep(.ev-maint) {
  background: repeating-linear-gradient(135deg, #fff4e5, #fff4e5 6px, #ffe9cc 6px, #ffe9cc 12px);
}
.calendar :deep(.ev-maint .fc-event-main) {
  color: #7a4a06;
}
@media (max-width: 1100px) {
  .booking-page {
    grid-template-columns: minmax(0, 1fr);
  }
  .side {
    position: static;
  }
}
.report-thumb {
  width: 48px;
  height: 48px;
  border-radius: var(--el-border-radius-small);
  border: 1px solid var(--lab-border);
  cursor: zoom-in;
}
</style>

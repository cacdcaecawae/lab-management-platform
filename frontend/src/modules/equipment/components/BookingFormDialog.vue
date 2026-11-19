<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { bookingsApi } from '../api'
import type { Booking, BookingKind, Equipment, ProjectBrief } from '@/api/types'
import { useAuthStore } from '@/stores/auth'
import { STATUS } from '@/utils/format'
import { useFieldErrors } from '@/utils/errors'

const visible = defineModel<boolean>({ required: true })
const props = defineProps<{
  equipment: Equipment[]
  projects: ProjectBrief[]
  // prefilled from the calendar selection or the equipment filter
  initial: { equipmentId: number | null; start: Date | null; end: Date | null }
}>()
const emit = defineEmits<{ saved: [booking: Booking] }>()

const auth = useAuthStore()
const form = reactive({
  equipment_id: null as number | null,
  kind: 'use' as BookingKind,
  start: null as Date | null,
  end: null as Date | null,
  project_id: null as number | null,
  purpose: '',
})
const errors = useFieldErrors(['equipment_id', 'kind', 'start_at', 'end_at', 'project_id', 'purpose'])
const saving = ref(false)

// Use bookings need an available device; maintenance (managers only) can reserve any.
const choices = computed(() =>
  props.equipment.filter((e) => form.kind === 'maintenance' || e.status === 'available' || e.id === form.equipment_id),
)
const unavailable = computed(() => {
  const picked = props.equipment.find((e) => e.id === form.equipment_id)
  return form.kind === 'use' && picked && picked.status !== 'available' ? picked : null
})

function nextHalfHour(): Date {
  const d = new Date()
  d.setMinutes(d.getMinutes() < 30 ? 30 : 60, 0, 0)
  return d
}

watch(visible, (v) => {
  if (!v) return
  const start = props.initial.start ?? nextHalfHour()
  Object.assign(form, {
    equipment_id: props.initial.equipmentId,
    kind: 'use',
    start,
    end: props.initial.end ?? new Date(start.getTime() + 2 * 3600_000),
    project_id: null,
    purpose: '',
  })
  errors.clear()
})

// Moving the start past the end would leave an impossible range; push the end out instead.
function onStartChange(start: Date | null) {
  if (start && form.end && form.end <= start) form.end = new Date(start.getTime() + 2 * 3600_000)
}

async function save() {
  saving.value = true
  try {
    const saved = await bookingsApi.create({
      equipment_id: form.equipment_id as number,
      kind: form.kind,
      start_at: form.start?.toISOString() ?? '',
      end_at: form.end?.toISOString() ?? '',
      project_id: form.project_id,
      purpose: form.purpose,
    })
    emit('saved', saved)
    visible.value = false
  } catch (e) {
    errors.handle(e)
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <el-dialog v-model="visible" title="新建预约" width="min(520px, 95vw)">
    <el-form label-position="top" @submit.prevent="save">
      <el-form-item v-if="auth.isManager" label="类型" :error="errors.fe('kind')">
        <el-radio-group v-model="form.kind">
          <el-radio value="use">使用</el-radio>
          <el-radio value="maintenance">维护（校准、维修占用）</el-radio>
        </el-radio-group>
      </el-form-item>
      <el-form-item label="设备" :error="errors.fe('equipment_id')" required>
        <el-select v-model="form.equipment_id" filterable placeholder="选择设备">
          <el-option v-for="e in choices" :key="e.id" :label="`${e.code} ${e.name}`" :value="e.id" />
        </el-select>
      </el-form-item>
      <el-alert
        v-if="unavailable"
        :title="`${unavailable.code} 当前为“${STATUS[unavailable.status].label}”，暂不能预约使用`"
        type="warning"
        :closable="false"
        class="form-alert"
      />
      <el-row :gutter="12">
        <el-col :xs="24" :sm="12">
          <el-form-item label="开始" :error="errors.fe('start_at')" required>
            <el-date-picker
              v-model="form.start"
              type="datetime"
              format="YYYY-MM-DD HH:mm"
              :clearable="false"
              style="width: 100%"
              @change="onStartChange"
            />
          </el-form-item>
        </el-col>
        <el-col :xs="24" :sm="12">
          <el-form-item label="结束" :error="errors.fe('end_at')" required>
            <el-date-picker v-model="form.end" type="datetime" format="YYYY-MM-DD HH:mm" :clearable="false" style="width: 100%" />
          </el-form-item>
        </el-col>
      </el-row>
      <el-form-item label="项目" :error="errors.fe('project_id')">
        <el-select v-model="form.project_id" filterable clearable placeholder="可不选">
          <el-option v-for="p in projects" :key="p.id" :label="p.name" :value="p.id" />
        </el-select>
      </el-form-item>
      <el-form-item label="用途" :error="errors.fe('purpose')">
        <el-input v-model="form.purpose" maxlength="200" placeholder="如 螺栓预紧力重复性测试" />
      </el-form-item>
      <el-alert v-for="msg in errors.others.value" :key="msg" :title="msg" type="error" :closable="false" />
    </el-form>
    <template #footer>
      <el-button @click="visible = false">取消</el-button>
      <el-button type="primary" :loading="saving" @click="save">预约</el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
.form-alert {
  margin-bottom: 18px;
}
</style>

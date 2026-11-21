<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { ApiError } from '@/api/client'
import { equipmentApi } from '../api'
import { membersApi } from '@/modules/members/api'
import { purchasesApi } from '@/modules/procurement/api'
import type { Equipment, EquipmentStatus, EquipmentWrite, PurchaseRef, UserBrief } from '@/api/types'
import { EQUIPMENT_STATUSES, STATUS, mergeById } from '@/utils/format'
import { showError, useFieldErrors } from '@/utils/errors'
import FormDialog from '@/components/FormDialog.vue'

const visible = defineModel<boolean>({ required: true })
const props = defineProps<{ equipment?: Equipment | null }>()
// stale: the status changed since the form opened; the dialog closed and the page should reload.
const emit = defineEmits<{ saved: [equipment: Equipment]; stale: [] }>()

const blank: EquipmentWrite = {
  code: '', name: '', model: '', category: '', location: '', custodian_id: null,
  status: 'available', purchase_date: null, calibration_due: null, notes: '', purchase_id: null,
}
const form = reactive<EquipmentWrite>({ ...blank })
// What the form showed when it opened. An edit sends only the fields that differ, so an untouched status
// cannot overwrite a "needs_check" set by an abnormal report while the dialog was open (F1).
let opened: EquipmentWrite = { ...blank }
const errors = useFieldErrors(Object.keys(blank))
const saving = ref(false)
const members = ref<UserBrief[]>([])
const options = computed(() => mergeById(members.value, [props.equipment?.custodian]))
// Arrived purchase requests (managers open this form, and they see the group's requests).
type PurchaseOption = PurchaseRef & { purpose?: string }
const arrived = ref<PurchaseOption[]>([])
const purchaseOptions = computed(() => mergeById<PurchaseOption>(arrived.value, [props.equipment?.purchase]))
let optionsLoaded = false

watch(visible, async (v) => {
  if (!v) return
  const e = props.equipment
  Object.assign(form, blank, e && {
    code: e.code, name: e.name, model: e.model, category: e.category, location: e.location,
    custodian_id: e.custodian?.id ?? null, status: e.status, purchase_date: e.purchase_date,
    calibration_due: e.calibration_due, notes: e.notes, purchase_id: e.purchase?.id ?? null,
  })
  opened = { ...form }
  errors.clear()
  if (optionsLoaded) return
  try {
    // shortcut: first 100 active members / arrived requests only; switch to remote search if a group gets larger.
    const [m, p] = await Promise.all([
      membersApi.list({ is_active: true, page_size: 100 }),
      purchasesApi.list({ status: 'arrived', page_size: 100 }),
    ])
    members.value = m.results
    arrived.value = p.results
    optionsLoaded = true
  } catch (e) {
    showError(e)
  }
})

// A cleared select or date picker gives undefined, which JSON drops; send null so the field is really cleared.
const value = (k: keyof EquipmentWrite) => form[k] ?? null

async function save() {
  const e = props.equipment
  const keys = (Object.keys(blank) as (keyof EquipmentWrite)[]).filter((k) => !e || value(k) !== (opened[k] ?? null))
  if (!keys.length) {
    visible.value = false // nothing changed: no request
    return
  }
  const body = Object.fromEntries(keys.map((k) => [k, value(k)])) as Partial<EquipmentWrite>
  saving.value = true
  try {
    const saved = e
      ? // A status change says which status it was decided on, so the server refuses it if that moved (R1).
        await equipmentApi.update(e.id, keys.includes('status') ? { ...body, status_seen: opened.status } : body)
      : await equipmentApi.create(body as EquipmentWrite)
    emit('saved', saved)
    visible.value = false
  } catch (err) {
    if (err instanceof ApiError && err.body.code === 'stale_status') {
      ElMessage.warning(err.message)
      visible.value = false
      emit('stale')
    } else errors.handle(err)
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <FormDialog v-model="visible" :title="equipment ? '编辑设备' : '新建设备'" :loading="saving" @submit="save">
    <div class="form-grid">
      <el-form-item label="设备编号" :error="errors.fe('code')" required>
        <el-input v-model="form.code" placeholder="如 UT-001" />
      </el-form-item>
      <el-form-item label="名称" :error="errors.fe('name')" required>
        <el-input v-model="form.name" />
      </el-form-item>
      <el-form-item label="型号" :error="errors.fe('model')">
        <el-input v-model="form.model" />
      </el-form-item>
      <el-form-item label="类别" :error="errors.fe('category')">
        <el-input v-model="form.category" placeholder="如 探伤仪、探头" />
      </el-form-item>
      <el-form-item label="存放位置" :error="errors.fe('location')">
        <el-input v-model="form.location" />
      </el-form-item>
      <el-form-item label="保管人" :error="errors.fe('custodian_id')">
        <el-select v-model="form.custodian_id" filterable clearable placeholder="选择保管人">
          <el-option v-for="m in options" :key="m.id" :label="m.name" :value="m.id" />
        </el-select>
      </el-form-item>
      <el-form-item label="购置日期" :error="errors.fe('purchase_date')">
        <el-date-picker v-model="form.purchase_date" type="date" value-format="YYYY-MM-DD" />
      </el-form-item>
      <el-form-item label="下次校准日期" :error="errors.fe('calibration_due')">
        <el-date-picker v-model="form.calibration_due" type="date" value-format="YYYY-MM-DD" />
      </el-form-item>
      <el-form-item label="采购申请（已到货）" :error="errors.fe('purchase_id')" class="span-all">
        <el-select v-model="form.purchase_id" filterable clearable placeholder="可不选">
          <el-option v-for="p in purchaseOptions" :key="p.id" :label="p.purpose ? `${p.code} ${p.purpose}` : p.code" :value="p.id" />
        </el-select>
      </el-form-item>
      <el-form-item label="状态" :error="errors.fe('status')" class="span-all">
        <el-radio-group v-model="form.status">
          <el-radio v-for="s in EQUIPMENT_STATUSES" :key="s" :value="s as EquipmentStatus">{{ STATUS[s].label }}</el-radio>
        </el-radio-group>
      </el-form-item>
      <el-form-item label="备注" :error="errors.fe('notes')" class="span-all">
        <el-input v-model="form.notes" type="textarea" :autosize="{ minRows: 2 }" />
      </el-form-item>
    </div>
    <el-alert v-for="msg in errors.others.value" :key="msg" :title="msg" type="error" :closable="false" />
  </FormDialog>
</template>

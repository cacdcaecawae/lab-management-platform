<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { Delete, Plus } from '@element-plus/icons-vue'
import { specimensApi } from '../api'
import { membersApi } from '@/modules/members/api'
import type { Defect, Specimen, SpecimenWrite, UserBrief } from '@/api/types'
import { DEFECT_KIND_LABELS, SPECIMEN_KIND_LABELS, SPECIMEN_STATUSES, STATUS, mergeById } from '@/utils/format'
import { showError, useFieldErrors } from '@/utils/errors'
import { suggest } from '@/api/suggestions'
import FormDialog from '@/components/FormDialog.vue'

const visible = defineModel<boolean>({ required: true })
const props = defineProps<{ specimen?: Specimen | null }>()
const emit = defineEmits<{ saved: [specimen: Specimen] }>()

const blank: SpecimenWrite = {
  code: '', name: '', kind: 'standard', material: '', dimensions: '', location: '', custodian_id: null,
  status: 'available', defects_public: false, notes: '', defects: [],
}
// el-input-number edits numbers; the server sends decimals as strings ("2.00") and takes either
type DefectRow = Omit<Defect, 'size_mm' | 'depth_mm'> & { size_mm: number | null; depth_mm: number | null }
const form = reactive<Omit<SpecimenWrite, 'defects'> & { defects: DefectRow[] }>({ ...blank, defects: [] })
let opened = '' // the form as JSON when it opened, per field: an edit sends only what changed
const errors = useFieldErrors(Object.keys(blank))
const saving = ref(false)
const members = ref<UserBrief[]>([])
const memberOptions = computed(() => mergeById(members.value, [props.specimen?.custodian]))
let membersLoaded = false

const toNumber = (v: string | number | null) => (v === null || v === '' ? null : Number(v))
const snapshot = () => Object.fromEntries(Object.entries(form).map(([k, v]) => [k, JSON.stringify(v ?? null)]))

watch(visible, async (v) => {
  if (!v) return
  const s = props.specimen
  Object.assign(form, blank, s && {
    code: s.code, name: s.name, kind: s.kind, material: s.material, dimensions: s.dimensions, location: s.location,
    custodian_id: s.custodian?.id ?? null, status: s.status, defects_public: s.defects_public, notes: s.notes,
  })
  form.defects = (s?.defects ?? []).map((d) => ({ ...d, size_mm: toNumber(d.size_mm), depth_mm: toNumber(d.depth_mm) }))
  opened = JSON.stringify(snapshot())
  errors.clear()
  if (membersLoaded) return
  try {
    // shortcut: the first 100 active members only; switch to remote search if a group gets larger.
    members.value = (await membersApi.list({ is_active: true, page_size: 100 })).results
    membersLoaded = true
  } catch (e) {
    showError(e)
  }
})

const addDefect = () => form.defects.push({ kind: 'fbh', size_mm: null, depth_mm: null, position: '', note: '' })

async function save() {
  const s = props.specimen
  const was = JSON.parse(opened || '{}') as Record<string, string>
  const now = snapshot()
  const keys = (Object.keys(blank) as (keyof SpecimenWrite)[]).filter((k) => !s || now[k] !== was[k])
  if (!keys.length) {
    visible.value = false // nothing changed: no request
    return
  }
  const body = Object.fromEntries(keys.map((k) => [k, form[k] ?? null])) as Partial<SpecimenWrite>
  saving.value = true
  try {
    emit('saved', s ? await specimensApi.update(s.id, body) : await specimensApi.create(body as SpecimenWrite))
    visible.value = false
  } catch (e) {
    errors.handle(e)
  } finally {
    saving.value = false
  }
}

</script>

<template>
  <FormDialog v-model="visible" :title="specimen ? '编辑试件' : '新建试件'" size="lg" :loading="saving" @submit="save">
    <div class="form-grid">
      <el-form-item label="编号" required :error="errors.fe('code')"><el-input v-model="form.code" /></el-form-item>
      <el-form-item label="名称" required :error="errors.fe('name')"><el-input v-model="form.name" /></el-form-item>
      <el-form-item label="类别" :error="errors.fe('kind')">
        <el-select v-model="form.kind" aria-label="类别">
          <el-option v-for="(label, k) in SPECIMEN_KIND_LABELS" :key="k" :label="label" :value="k" />
        </el-select>
      </el-form-item>
      <el-form-item label="材料" :error="errors.fe('material')"><el-autocomplete v-model="form.material" :fetch-suggestions="suggest('specimen.material')" placeholder="如 20 钢、6061 铝" /></el-form-item>
      <el-form-item label="尺寸" :error="errors.fe('dimensions')"><el-input v-model="form.dimensions" placeholder="如 300×100×25 mm" /></el-form-item>
      <el-form-item label="存放位置" :error="errors.fe('location')"><el-autocomplete v-model="form.location" :fetch-suggestions="suggest('specimen.location')" /></el-form-item>
      <el-form-item label="保管人" :error="errors.fe('custodian_id')">
        <el-select v-model="form.custodian_id" aria-label="保管人" placeholder="选择保管人" clearable filterable>
          <el-option v-for="m in memberOptions" :key="m.id" :label="m.name" :value="m.id" />
        </el-select>
      </el-form-item>
      <el-form-item class="span-2" label="状态" :error="errors.fe('status')">
        <el-radio-group v-model="form.status">
          <el-radio v-for="st in SPECIMEN_STATUSES" :key="st" :value="st">{{ STATUS[st].label }}</el-radio>
        </el-radio-group>
      </el-form-item>
    </div>

    <el-form-item :error="errors.fe('defects')">
      <template #label>
        <span>缺陷参数</span>
        <el-switch v-model="form.defects_public" aria-label="缺陷参数对学生公开" class="public-switch" inline-prompt active-text="对学生公开" inactive-text="学生看不到" />
      </template>
      <div class="defects">
        <div v-for="(d, i) in form.defects" :key="i" class="defect-row">
          <el-select v-model="d.kind" :aria-label="`第 ${i + 1} 个缺陷的类型`" class="kind">
            <el-option v-for="(label, k) in DEFECT_KIND_LABELS" :key="k" :label="label" :value="k" />
          </el-select>
          <el-input-number v-model="d.size_mm" :aria-label="`第 ${i + 1} 个缺陷的尺寸`" placeholder="尺寸 mm" :min="0" :precision="2" :controls="false" />
          <el-input-number v-model="d.depth_mm" :aria-label="`第 ${i + 1} 个缺陷的埋深`" placeholder="埋深 mm" :min="0" :precision="2" :controls="false" />
          <el-input v-model="d.position" :aria-label="`第 ${i + 1} 个缺陷的位置`" placeholder="位置，如 距左端 50 mm" />
          <el-input v-model="d.note" :aria-label="`第 ${i + 1} 个缺陷的备注`" placeholder="备注" />
          <el-button :icon="Delete" text :aria-label="`删除第 ${i + 1} 个缺陷`" @click="form.defects.splice(i, 1)" />
        </div>
        <el-button :icon="Plus" @click="addDefect">添加缺陷</el-button>
      </div>
    </el-form-item>

    <el-form-item label="备注" :error="errors.fe('notes')"><el-input v-model="form.notes" type="textarea" :rows="2" /></el-form-item>
    <el-alert v-for="msg in errors.others.value" :key="msg" :title="msg" type="error" :closable="false" />
  </FormDialog>
</template>

<style scoped>
.public-switch {
  margin-left: 12px;
}
.defects {
  display: flex;
  flex-direction: column;
  gap: 8px;
  width: 100%;
}
.defect-row {
  display: grid;
  grid-template-columns: 110px 110px 110px 1fr 1fr 32px;
  gap: 8px;
}
.defect-row :deep(.el-input-number) {
  width: 100%;
}
@media (max-width: 640px) {
  .defect-row {
    grid-template-columns: 1fr 1fr;
  }
}
</style>

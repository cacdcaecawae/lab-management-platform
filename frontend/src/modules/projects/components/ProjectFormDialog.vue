<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { membersApi } from '@/modules/members/api'
import { projectsApi } from '@/modules/projects/api'
import type { Project, ProjectStatus, ProjectWrite, UserBrief } from '@/api/types'
import { useAuthStore } from '@/stores/auth'
import { mergeById } from '@/utils/format'
import { showError, useFieldErrors } from '@/utils/errors'
import FormDialog from '@/components/FormDialog.vue'

const visible = defineModel<boolean>({ required: true })
const props = defineProps<{ project?: Project | null }>()
const emit = defineEmits<{ saved: [project: Project] }>()

const auth = useAuthStore()
const blank = { name: '', leader_id: null as number | null, member_ids: [] as number[], stage: '', status: 'active' as ProjectStatus, description: '' }
const form = reactive({ ...blank })
const errors = useFieldErrors(Object.keys(blank))
const saving = ref(false)
const members = ref<UserBrief[]>([])
const options = computed(() => mergeById(members.value, [props.project?.leader, ...(props.project?.members ?? [])]))
// Only managers / advisors may change the leader (a leader sending leader_id gets 403).
const canChangeLeader = computed(() => !props.project || auth.isSupervisor)

watch(visible, async (v) => {
  if (!v) return
  const p = props.project
  Object.assign(form, blank, p && {
    name: p.name,
    leader_id: p.leader.id,
    member_ids: p.members.map((m) => m.id),
    stage: p.stage,
    status: p.status,
    description: p.description,
  })
  errors.clear()
  if (members.value.length) return
  try {
    // shortcut: first 100 active members only; switch to remote search if a group gets larger.
    members.value = (await membersApi.list({ is_active: true, page_size: 100 })).results
  } catch (e) {
    showError(e)
  }
})

async function save() {
  const p = props.project
  const body: Partial<ProjectWrite> = { ...form, leader_id: form.leader_id ?? undefined }
  if (p && (!auth.isSupervisor || form.leader_id === p.leader.id)) delete body.leader_id
  saving.value = true
  try {
    const saved = p ? await projectsApi.update(p.id, body) : await projectsApi.create(body as ProjectWrite)
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
  <FormDialog v-model="visible" :title="project ? '编辑项目' : '新建项目'" :loading="saving" @submit="save">
    <el-form-item label="项目名称" :error="errors.fe('name')" required>
      <el-input v-model="form.name" />
    </el-form-item>
    <el-form-item label="负责人" :error="errors.fe('leader_id')" required>
      <el-select v-model="form.leader_id" filterable :disabled="!canChangeLeader" placeholder="选择负责人">
        <el-option v-for="m in options" :key="m.id" :label="m.name" :value="m.id" />
      </el-select>
    </el-form-item>
    <el-form-item label="成员（负责人自动计入）" :error="errors.fe('member_ids')">
      <el-select v-model="form.member_ids" multiple filterable placeholder="选择成员">
        <el-option v-for="m in options" :key="m.id" :label="m.name" :value="m.id" />
      </el-select>
    </el-form-item>
    <el-form-item label="当前阶段" :error="errors.fe('stage')">
      <el-input v-model="form.stage" />
    </el-form-item>
    <el-form-item label="状态" :error="errors.fe('status')">
      <el-radio-group v-model="form.status">
        <el-radio value="active">进行中</el-radio>
        <el-radio value="closed">已结束</el-radio>
      </el-radio-group>
    </el-form-item>
    <el-form-item label="说明" :error="errors.fe('description')">
      <el-input v-model="form.description" type="textarea" :autosize="{ minRows: 3 }" />
    </el-form-item>
    <el-alert v-for="msg in errors.others.value" :key="msg" :title="msg" type="error" :closable="false" />
  </FormDialog>
</template>

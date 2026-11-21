<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { authApi } from '@/api/auth'
import { useAuthStore } from '@/stores/auth'
import { ROLE_LABELS } from '@/utils/format'
import { useFieldErrors } from '@/utils/errors'
import FormDialog from '@/components/FormDialog.vue'

// 个人信息 (DESIGN.md): the person keeps their email, phone and research direction up to date. Name, login name,
// role and group are shown as text: managers change them in 成员, ops in 系统管理.
const open = defineModel<boolean>({ required: true })
const auth = useAuthStore()
const role = computed(() => (auth.user?.is_superuser ? '运维' : ROLE_LABELS[auth.user?.role ?? '']))
// Who can change the rest (members page: managers handle students and themselves; ops handles advisors and managers).
const whoChanges = computed(() => {
  if (!auth.user || auth.user.is_superuser) return ''
  if (auth.user.role === 'manager') return '姓名、学号 / 工号在"成员"里自己那一行修改。'
  return auth.user.role === 'advisor' ? '姓名、学号 / 工号要改，请联系运维。' : '姓名、学号 / 工号要改，请联系课题组管理员。'
})
const form = reactive({ email: '', phone: '', research_direction: '' })
const errors = useFieldErrors(Object.keys(form))
const saving = ref(false)

watch(
  open,
  (shown) => {
    if (!shown || !auth.user) return
    const { email, phone, research_direction } = auth.user
    Object.assign(form, { email, phone, research_direction })
    errors.clear()
  },
  { immediate: true },
)

async function save() {
  saving.value = true
  try {
    auth.user = await authApi.updateMe(form)
    ElMessage.success('已保存')
    open.value = false
  } catch (e) {
    errors.handle(e)
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <FormDialog v-model="open" title="个人信息" size="sm" :loading="saving" @submit="save">
    <div class="form-grid">
      <el-form-item label="姓名"><span>{{ auth.user?.name }}</span></el-form-item>
      <el-form-item label="学号 / 工号"><span class="code">{{ auth.user?.username }}</span></el-form-item>
      <el-form-item label="角色"><span>{{ role }}</span></el-form-item>
      <el-form-item v-if="auth.user?.group" label="课题组"><span>{{ auth.user.group.name }}</span></el-form-item>
    </div>
    <el-form-item label="邮箱" :error="errors.fe('email')">
      <el-input v-model="form.email" type="email" autocomplete="email" />
    </el-form-item>
    <div class="form-grid">
      <el-form-item label="电话" :error="errors.fe('phone')">
        <el-input v-model="form.phone" type="tel" autocomplete="tel" />
      </el-form-item>
      <el-form-item label="研究方向" :error="errors.fe('research_direction')">
        <el-input v-model="form.research_direction" />
      </el-form-item>
    </div>
    <el-alert v-for="msg in errors.others.value" :key="msg" :title="msg" type="error" :closable="false" />
    <template v-if="whoChanges" #after>
      <p class="note">{{ whoChanges }}</p>
    </template>
  </FormDialog>
</template>

<style scoped>
.note {
  margin: 4px 0 0;
  color: var(--lab-text-3);
  font-size: 13px;
}
</style>

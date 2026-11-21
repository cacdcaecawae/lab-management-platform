<script setup lang="ts">
import { reactive, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { authApi } from '@/api/auth'
import { useAuthStore } from '@/stores/auth'
import { useFieldErrors } from '@/utils/errors'
import FormDialog from '@/components/FormDialog.vue'
import AccountCard from './AccountCard.vue'

// 个人信息 (DESIGN.md): who you are on top (click the picture to change it, saved at once), then the contact
// details you keep up to date yourself. Name, login name and role are set by managers in 成员 / ops in 系统管理.
const open = defineModel<boolean>({ required: true })
const auth = useAuthStore()
const form = reactive({ email: '', phone: '', wechat: '', research_direction: '' })
const errors = useFieldErrors(Object.keys(form))
const saving = ref(false)

watch(
  open,
  (shown) => {
    if (!shown || !auth.user) return
    const { email, phone, wechat, research_direction } = auth.user
    Object.assign(form, { email, phone, wechat, research_direction })
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
    <template #before>
      <AccountCard class="head" :size="64" editable />
    </template>
    <div class="form-grid">
      <el-form-item label="邮箱" :error="errors.fe('email')">
        <el-input v-model="form.email" type="email" autocomplete="email" />
      </el-form-item>
      <el-form-item label="电话" :error="errors.fe('phone')">
        <el-input v-model="form.phone" type="tel" autocomplete="tel" />
      </el-form-item>
      <el-form-item label="微信号" :error="errors.fe('wechat')">
        <el-input v-model="form.wechat" />
      </el-form-item>
      <el-form-item label="研究方向" :error="errors.fe('research_direction')">
        <el-input v-model="form.research_direction" />
      </el-form-item>
    </div>
    <el-alert v-for="msg in errors.others.value" :key="msg" :title="msg" type="error" :closable="false" />
  </FormDialog>
</template>

<style scoped>
.head {
  margin-bottom: 20px;
  padding-bottom: 20px;
  border-bottom: 1px solid var(--lab-border);
}
</style>

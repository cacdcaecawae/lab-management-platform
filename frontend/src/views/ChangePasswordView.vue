<script setup lang="ts">
import { reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { ApiError } from '@/api/client'
import { useAuthStore } from '@/stores/auth'
import { postAuthTarget } from '@/router/post-auth'
import icon from '@/assets/phase-icon.png'

const auth = useAuthStore()
const router = useRouter()
const route = useRoute()
const form = reactive({ old: '', next: '', confirm: '' })
const errors = ref<string[]>([])

async function submit() {
  errors.value = []
  if (form.next !== form.confirm) {
    errors.value = ['两次输入的新密码不一致']
    return
  }
  try {
    await auth.changePassword(form.old, form.next)
    ElMessage.success('密码已修改')
    await router.replace(postAuthTarget(router, route.query.next) ?? { name: 'workbench' })
  } catch (e) {
    if (!(e instanceof ApiError)) throw e
    errors.value = e.body.errors ? Object.values(e.body.errors).flat() : [e.message]
  }
}
</script>

<template>
  <div class="auth-page">
    <div class="auth-panel">
      <img class="auth-logo" :src="icon" alt="" />
      <h2>修改密码</h2>
      <p v-if="auth.user?.must_change_password" class="auth-sub">首次登录，请先修改初始密码。</p>
      <el-form label-position="top" size="large" @submit.prevent="submit">
        <el-form-item label="原密码"><el-input v-model="form.old" type="password" show-password /></el-form-item>
        <el-form-item label="新密码"><el-input v-model="form.next" type="password" show-password /></el-form-item>
        <el-form-item label="确认新密码"><el-input v-model="form.confirm" type="password" show-password /></el-form-item>
        <el-alert v-for="msg in errors" :key="msg" :title="msg" type="error" :closable="false" class="auth-alert" />
        <el-button type="primary" native-type="submit" class="auth-submit">确认修改</el-button>
      </el-form>
    </div>
  </div>
</template>

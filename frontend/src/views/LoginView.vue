<script setup lang="ts">
import { reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ApiError } from '@/api/client'
import { useAuthStore } from '@/stores/auth'
import { postAuthTarget } from '@/router/post-auth'

const auth = useAuthStore()
const router = useRouter()
const route = useRoute()
const form = reactive({ username: '', password: '' })
const error = ref('')
const loading = ref(false)

async function submit() {
  error.value = ''
  loading.value = true
  try {
    await auth.login(form.username, form.password)
    await router.replace(postAuthTarget(router, route.query.next) ?? { name: 'workbench' })
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : '登录失败，请稍后重试'
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="auth-page">
    <div class="auth-panel">
      <span class="auth-logo" aria-hidden="true">课</span>
      <h2>课题组管理平台</h2>
      <el-form label-position="top" size="large" @submit.prevent="submit">
        <el-form-item label="学号 / 工号">
          <el-input v-model="form.username" autocomplete="username" />
        </el-form-item>
        <el-form-item label="密码">
          <el-input v-model="form.password" type="password" show-password autocomplete="current-password" />
        </el-form-item>
        <el-alert v-if="error" :title="error" type="error" :closable="false" show-icon class="auth-alert" />
        <el-button type="primary" native-type="submit" :loading="loading" class="auth-submit">登录</el-button>
      </el-form>
      <p class="auth-sub">还没有账号？打开课题组管理员发的注册链接申请。</p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { reactive, ref } from 'vue'
import { useRoute } from 'vue-router'
import { ApiError } from '@/api/client'
import { authApi } from '@/api/auth'
import icon from '@/assets/phase-icon.png'

// The code in the group's link decides which group the application goes to.
const code = String(useRoute().query.code ?? '')
const form = reactive({ username: '', name: '', email: '', password: '', confirm: '' })
const errors = ref<string[]>([])
const loading = ref(false)
const done = ref(false)

async function submit() {
  errors.value = []
  if (form.password !== form.confirm) {
    errors.value = ['两次输入的密码不一致']
    return
  }
  loading.value = true
  try {
    await authApi.csrf()
    const { confirm: _, ...body } = form
    await authApi.register({ code, ...body })
    done.value = true
  } catch (e) {
    if (!(e instanceof ApiError)) throw e
    errors.value = e.body.errors ? Object.values(e.body.errors).flat() : [e.message]
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="auth-page">
    <div class="auth-panel">
      <img class="auth-logo" :src="icon" alt="" />
      <h2>学生注册</h2>
      <template v-if="done">
        <p class="auth-sub">已提交，等待课题组管理员审核。审核通过后，用学号和刚才设的密码登录。</p>
        <router-link :to="{ name: 'login' }">返回登录</router-link>
      </template>
      <template v-else-if="!code">
        <p class="auth-sub">注册要用课题组管理员发的注册链接打开，请向管理员索取。</p>
        <router-link :to="{ name: 'login' }">返回登录</router-link>
      </template>
      <el-form v-else label-position="top" size="large" @submit.prevent="submit">
        <el-form-item label="学号（登录名）" required>
          <el-input v-model="form.username" autocomplete="username" />
        </el-form-item>
        <el-form-item label="姓名" required><el-input v-model="form.name" autocomplete="name" /></el-form-item>
        <el-form-item label="邮箱"><el-input v-model="form.email" autocomplete="email" /></el-form-item>
        <el-form-item label="密码" required>
          <el-input v-model="form.password" type="password" show-password autocomplete="new-password" />
        </el-form-item>
        <el-form-item label="确认密码" required>
          <el-input v-model="form.confirm" type="password" show-password autocomplete="new-password" />
        </el-form-item>
        <el-alert v-for="msg in errors" :key="msg" :title="msg" type="error" :closable="false" class="auth-alert" />
        <el-button type="primary" native-type="submit" :loading="loading" class="auth-submit">提交申请</el-button>
      </el-form>
    </div>
  </div>
</template>

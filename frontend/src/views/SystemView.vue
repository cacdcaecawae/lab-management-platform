<script setup lang="ts">
import { ref } from 'vue'
import SystemAccounts from '@/components/SystemAccounts.vue'
import SystemGroups from '@/components/SystemGroups.vue'
import SystemMail from '@/components/SystemMail.vue'

const tab = ref('mail')
</script>

<template>
  <el-card class="card">
    <el-tabs v-model="tab">
      <el-tab-pane label="邮件" name="mail"><SystemMail /></el-tab-pane>
      <el-tab-pane label="课题组" name="groups" lazy><SystemGroups /></el-tab-pane>
      <el-tab-pane label="账号" name="accounts" lazy><SystemAccounts /></el-tab-pane>
    </el-tabs>
  </el-card>
</template>

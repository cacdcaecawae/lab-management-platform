<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { systemApi, type StorageInfo } from '@/modules/system/api'
import type { VersionInfo } from '@/api/types'
import SystemAccounts from '@/modules/system/components/SystemAccounts.vue'
import SystemGroups from '@/modules/system/components/SystemGroups.vue'
import SystemMail from '@/modules/system/components/SystemMail.vue'
import SystemVersion from '@/modules/system/components/SystemVersion.vue'
import StorageUsage from '@/components/StorageUsage.vue'
import SystemLoginEvents from '@/components/SystemLoginEvents.vue'
import SystemStorage from '@/modules/system/components/SystemStorage.vue'
import { showError } from '@/utils/errors'

const tab = ref('mail')
// Loaded here, not in the tabs, so the tab labels can say an update is waiting or backups need attention.
const version = ref<VersionInfo | null>(null)
const storage = ref<StorageInfo | null>(null)
onMounted(() => {
  systemApi.version().then((v) => (version.value = v), showError)
  systemApi.storage().then((s) => (storage.value = s), showError)
})
</script>

<template>
  <el-card class="card">
    <el-tabs v-model="tab">
      <el-tab-pane label="邮件" name="mail"><SystemMail /></el-tab-pane>
      <el-tab-pane label="课题组" name="groups" lazy><SystemGroups /></el-tab-pane>
      <el-tab-pane label="账号" name="accounts" lazy><SystemAccounts /></el-tab-pane>
      <el-tab-pane :label="storage?.attention ? '存储与备份 · 需处理' : '存储与备份'" name="storage-status" lazy>
        <SystemStorage v-model:info="storage" />
      </el-tab-pane>
      <el-tab-pane label="存储用量" name="storage" lazy><StorageUsage ops /></el-tab-pane>
      <el-tab-pane :label="version?.update_available ? '版本 · 有更新' : '版本'" name="version">
        <SystemVersion v-if="version" v-model:info="version" />
      </el-tab-pane>
      <el-tab-pane label="登录记录" name="logins" lazy><SystemLoginEvents /></el-tab-pane>
    </el-tabs>
  </el-card>
</template>

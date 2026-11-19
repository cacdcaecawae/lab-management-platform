<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { systemApi } from '@/api/system'
import type { VersionInfo } from '@/api/types'
import SystemAccounts from '@/components/SystemAccounts.vue'
import SystemGroups from '@/components/SystemGroups.vue'
import SystemMail from '@/components/SystemMail.vue'
import SystemStorage from '@/components/SystemStorage.vue'
import SystemVersion from '@/components/SystemVersion.vue'
import { showError } from '@/utils/errors'

const tab = ref('mail')
// Loaded here, not in the tab, so the tab label can say an update is waiting.
const version = ref<VersionInfo | null>(null)
onMounted(async () => {
  try {
    version.value = await systemApi.version()
  } catch (e) {
    showError(e)
  }
})
</script>

<template>
  <el-card class="card">
    <el-tabs v-model="tab">
      <el-tab-pane label="邮件" name="mail"><SystemMail /></el-tab-pane>
      <el-tab-pane label="课题组" name="groups" lazy><SystemGroups /></el-tab-pane>
      <el-tab-pane label="账号" name="accounts" lazy><SystemAccounts /></el-tab-pane>
      <el-tab-pane label="存储与备份" name="storage-status" lazy><SystemStorage /></el-tab-pane>
      <el-tab-pane :label="version?.update_available ? '版本 · 有更新' : '版本'" name="version">
        <SystemVersion v-if="version" :info="version" />
      </el-tab-pane>
    </el-tabs>
  </el-card>
</template>

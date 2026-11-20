<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { systemApi, type StorageInfo } from '@/modules/system/api'
import { showError } from '@/utils/errors'

const info = ref<StorageInfo | null>(null)
const checking = ref(false)

async function check() {
  checking.value = true
  info.value = null
  try {
    info.value = await systemApi.storage()
  } catch (error) {
    showError(error)
  } finally {
    checking.value = false
  }
}

onMounted(check)
</script>

<template>
  <el-descriptions title="主存储" :column="1" border>
    <el-descriptions-item label="附件保存位置">
      {{ info ? (info.primary === 'nas' ? '专用 NAS 目录' : '服务器本地卷') : '未取得状态' }}
    </el-descriptions-item>
    <el-descriptions-item label="NAS 连接检查">
      {{ !info ? '未取得状态' : info.nas_ready === null ? '未启用' : info.nas_ready ? '已识别专用目录' : '不可用，文件操作已暂停' }}
    </el-descriptions-item>
  </el-descriptions>
  <p>NAS 挂载和凭据由服务器运维配置。此处只检查读取，不写入文件，也不代表备份已成功。</p>
  <el-button :loading="checking" @click="check">检查连接</el-button>
  <h3>备份</h3>
  <p>备份需保存在独立目标。请由运维在服务器查看备份任务日志和恢复演练结果。</p>
</template>

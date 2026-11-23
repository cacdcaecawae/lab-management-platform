import { defineStore } from 'pinia'
import { ref } from 'vue'
import { opsStatusApi, type StorageInfo } from '@/api/opsStatus'
import type { VersionInfo } from '@/api/types'
import { showError } from '@/utils/errors'

// What the ops sidebar marks (存储与备份 需处理, 版本 有更新). Loaded once for an ops account, and again by the next
// 系统管理 page opened if that failed; the two pages write their own fresh checks back here, so the marks follow.
export const useOpsStore = defineStore('ops', () => {
  const storage = ref<StorageInfo | null>(null)
  const version = ref<VersionInfo | null>(null)
  let started = false
  function load() {
    if (started) return
    started = true
    const failed = (error: unknown) => {
      started = false
      showError(error)
    }
    opsStatusApi.storage().then((s) => (storage.value = s), failed)
    opsStatusApi.version().then((v) => (version.value = v), failed)
  }
  return { storage, version, load }
})

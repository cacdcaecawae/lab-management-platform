import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { VersionInfo } from '@/api/types'
import { systemApi, type StorageInfo } from '@/modules/system/api'
import { showError } from '@/utils/errors'

// What the ops sidebar marks (存储与备份 需处理, 版本 有更新). Loaded once for an ops account; the two pages write
// their own fresh checks back here, so the marks follow.
export const useOpsStore = defineStore('ops', () => {
  const storage = ref<StorageInfo | null>(null)
  const version = ref<VersionInfo | null>(null)
  let started = false
  function load() {
    if (started) return
    started = true
    systemApi.storage().then((s) => (storage.value = s), showError)
    systemApi.version().then((v) => (version.value = v), showError)
  }
  return { storage, version, load }
})

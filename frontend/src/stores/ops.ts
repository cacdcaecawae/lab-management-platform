import { defineStore } from 'pinia'
import { ref, watch } from 'vue'
import { opsStatusApi, type StorageInfo } from '@/api/opsStatus'
import type { VersionInfo } from '@/api/types'
import { useAuthStore } from '@/stores/auth'
import { showError } from '@/utils/errors'

// What the ops sidebar marks (存储与备份 需处理, 版本 有更新). Loaded once for an ops account, and again by the next
// 系统管理 page opened if that failed; the two pages write their own fresh checks back here, so the marks follow.
export const useOpsStore = defineStore('ops', () => {
  const auth = useAuthStore()
  const storage = ref<StorageInfo | null>(null)
  const version = ref<VersionInfo | null>(null)
  let started = false
  let generation = 0
  // Signed out, or another account signed in in this tab: what was loaded (or is still on its way) was the last one's.
  watch(
    () => auth.user?.id,
    () => {
      generation++
      started = false
      storage.value = null
      version.value = null
    },
    { flush: 'sync' }, // at once: the menu of the new account may ask for its own status in the same tick
  )
  function load() {
    if (started) return
    started = true
    const mine = generation
    const failed = (error: unknown) => {
      if (mine !== generation) return
      started = false
      showError(error)
    }
    opsStatusApi.storage().then((s) => mine === generation && (storage.value = s), failed)
    opsStatusApi.version().then((v) => mine === generation && (version.value = v), failed)
  }
  return { storage, version, load }
})

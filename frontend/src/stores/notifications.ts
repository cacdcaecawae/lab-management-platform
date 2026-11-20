import { defineStore } from 'pinia'
import { ref } from 'vue'
import { notificationsApi } from '@/api/notifications'
import { useAuthStore } from './auth'

export const useNotificationsStore = defineStore('notifications', () => {
  const unread = ref(0)
  let revision = 0

  function reset() {
    revision++
    unread.value = 0
  }

  async function refresh() {
    const current = ++revision
    const auth = useAuthStore()
    const recipient = auth.user?.id
    const group = auth.user?.group?.id
    const role = auth.user?.role
    if (!group || auth.user?.must_change_password) return reset()
    try {
      const { count } = await notificationsApi.count()
      if (current === revision && auth.user?.id === recipient && auth.user?.group?.id === group && auth.user?.role === role) {
        unread.value = count
      }
    } catch {
      // Polling is best effort. Explicit mark/read/list failures show their actual error.
    }
  }

  return { unread, refresh, reset }
})

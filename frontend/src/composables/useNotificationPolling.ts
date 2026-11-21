import { onMounted, onUnmounted, watch } from 'vue'
import { useRoute } from 'vue-router'
import { useNotificationsStore } from '@/stores/notifications'

// Keeps the unread count behind the menu's 通知 badge fresh: every minute while the tab is visible, and on navigation.
export function useNotificationPolling() {
  const route = useRoute()
  const store = useNotificationsStore()
  let poll: ReturnType<typeof setInterval> | undefined

  function refreshIfVisible() {
    if (document.visibilityState === 'visible') void store.refresh()
  }

  function restart() {
    if (poll !== undefined) clearInterval(poll)
    poll = undefined
    if (document.visibilityState === 'visible') {
      refreshIfVisible()
      poll = setInterval(refreshIfVisible, 60_000)
    }
  }

  onMounted(() => {
    document.addEventListener('visibilitychange', restart)
    restart()
  })
  onUnmounted(() => {
    if (poll !== undefined) clearInterval(poll)
    document.removeEventListener('visibilitychange', restart)
    store.reset()
  })
  watch(() => route.fullPath, refreshIfVisible)
}

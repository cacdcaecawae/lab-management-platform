import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { authApi } from '@/api/auth'
import { ApiError } from '@/api/client'
import type { Me } from '@/api/types'

export const useAuthStore = defineStore('auth', () => {
  const user = ref<Me | null>(null)
  const loaded = ref(false)
  const isSupervisor = computed(() => user.value?.is_supervisor ?? false)
  // Managers (not advisors) maintain equipment and consumables.
  const isManager = computed(() => user.value?.role === 'manager')
  const isSuperuser = computed(() => user.value?.is_superuser ?? false)

  // Called once by the router guard; a 403 just means "not logged in".
  async function load() {
    if (loaded.value) return
    try {
      user.value = await authApi.me()
    } catch (e) {
      if (!(e instanceof ApiError && e.status === 403)) throw e
      user.value = null
    }
    loaded.value = true
  }

  async function login(username: string, password: string) {
    await authApi.csrf()
    user.value = await authApi.login(username, password)
    loaded.value = true
  }

  async function logout() {
    await authApi.logout()
    user.value = null
  }

  async function changePassword(oldPassword: string, newPassword: string) {
    await authApi.changePassword(oldPassword, newPassword)
    user.value = await authApi.me()
  }

  return { user, loaded, isSupervisor, isManager, isSuperuser, load, login, logout, changePassword }
})

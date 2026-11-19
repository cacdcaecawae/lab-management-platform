import { api } from '@/api/client'
import type { Dashboard } from '@/api/types'

export const dashboardApi = {
  get: () => api.get<Dashboard>('/api/dashboard/'),
}

import { api, type Page } from './client'

export interface SiteNotification {
  id: number
  title: string
  body: string
  link: string
  created_at: string
  read_at: string | null
}

export const notificationsApi = {
  list: (q?: { page?: number; page_size?: number; unread?: 1 | ''; module?: string }) => api.get<Page<SiteNotification>>('/api/notifications/', q),
  count: () => api.get<{ count: number }>('/api/notifications/unread-count/'),
  read: (id: number) => api.post<SiteNotification>(`/api/notifications/${id}/read/`, {}),
  readAll: () => api.post<{ updated: number }>('/api/notifications/read-all/', {}),
}

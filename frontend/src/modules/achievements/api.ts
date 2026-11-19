import { api, withQuery, type Page } from '@/api/client'
import type { Achievement, AchievementWrite, HistoryEntry, ListQuery } from '@/api/types'

export const achievementsApi = {
  // q: type, status (comma separated), year, member, search
  list: (q?: ListQuery) => api.get<Page<Achievement>>('/api/achievements/', q),
  create: (body: AchievementWrite) => api.post<Achievement>('/api/achievements/', body),
  update: (id: number, body: Partial<AchievementWrite>) => api.patch<Achievement>(`/api/achievements/${id}/`, body),
  remove: (id: number) => api.delete(`/api/achievements/${id}/`),
  history: (id: number) => api.get<HistoryEntry[]>(`/api/achievements/${id}/history/`),
  uploadFulltext: (id: number, file: File) => {
    const form = new FormData()
    form.append('file', file)
    return api.post<Achievement>(`/api/achievements/${id}/fulltext/`, form)
  },
  removeFulltext: (id: number) => api.delete(`/api/achievements/${id}/fulltext/`),
  // plain links: the browser downloads with the session cookie; files=1 adds the full texts (a .zip)
  exportUrl: (q: ListQuery, files = false) => withQuery('/api/achievements/export/', { ...q, files: files ? 1 : undefined }),
}

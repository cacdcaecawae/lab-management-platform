import { api, type Page } from '@/api/client'
import { uploadForm } from '@/modules/datasets/api'
import type { ActionItem, HistoryEntry, ListQuery, Meeting, MeetingFile, MeetingWrite, MyActionItem } from '@/api/types'

export const meetingsApi = {
  list: (q?: ListQuery) => api.get<Page<Meeting>>('/api/meetings/', q),
  get: (id: number) => api.get<Meeting>(`/api/meetings/${id}/`),
  create: (body: MeetingWrite) => api.post<Meeting>('/api/meetings/', body),
  update: (id: number, body: Partial<MeetingWrite>) => api.patch<Meeting>(`/api/meetings/${id}/`, body),
  remove: (id: number) => api.delete(`/api/meetings/${id}/`),
  history: (id: number) => api.get<HistoryEntry[]>(`/api/meetings/${id}/history/`),
  upload: (id: number, file: File, onProgress?: (percent: number) => void) => {
    const form = new FormData()
    form.append('file', file)
    return uploadForm<MeetingFile>(`/api/meetings/${id}/files/`, form, onProgress) // slides can be large: show progress
  },
  removeFile: (fileId: number) => api.delete(`/api/meeting-files/${fileId}/`),
  setDone: (itemId: number, done: boolean) => api.post<ActionItem>(`/api/action-items/${itemId}/done/`, { done }),
  actions: (q?: ListQuery) => api.get<Page<MyActionItem>>('/api/action-items/', q),
}

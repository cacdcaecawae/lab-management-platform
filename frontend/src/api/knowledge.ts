import { api, type Page } from './client'
import { uploadForm } from './datasets'
import type { Doc, DocDetail, DocVersion, DocWrite, HistoryEntry, ListQuery } from './types'

export const docsApi = {
  // q: search, category, equipment, tag
  list: (q?: ListQuery) => api.get<Page<Doc>>('/api/docs/', q),
  get: (id: number) => api.get<DocDetail>(`/api/docs/${id}/`),
  create: (body: DocWrite) => api.post<DocDetail>('/api/docs/', body),
  update: (id: number, body: Partial<DocWrite>) => api.patch<DocDetail>(`/api/docs/${id}/`, body),
  remove: (id: number) => api.delete(`/api/docs/${id}/`),
  history: (id: number) => api.get<HistoryEntry[]>(`/api/docs/${id}/history/`),
  // SDK packages can be large: report upload progress
  addVersion: (id: number, file: File, note: string, onProgress?: (percent: number) => void) => {
    const form = new FormData()
    form.append('file', file)
    form.append('note', note)
    return uploadForm<DocVersion>(`/api/docs/${id}/versions/`, form, onProgress)
  },
}

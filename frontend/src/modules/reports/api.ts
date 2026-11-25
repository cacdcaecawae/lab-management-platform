import { api, type Page } from '@/api/client'
import { uploadForm } from '@/modules/datasets/api'
import type {
  FeedbackWrite,
  HistoryEntry,
  ListQuery,
  ReportFile,
  ReportWrite,
  UserBrief,
  WeekRecords,
  WeeklyReport,
  WeeklyReportDigest,
} from '@/api/types'

export const reportsApi = {
  list: (q?: ListQuery) => api.get<Page<WeeklyReport>>('/api/reports/', q),
  get: (id: number) => api.get<WeeklyReport>(`/api/reports/${id}/`),
  create: (body: ReportWrite) => api.post<WeeklyReport>('/api/reports/', body),
  update: (id: number, body: Partial<ReportWrite>) => api.patch<WeeklyReport>(`/api/reports/${id}/`, body),
  remove: (id: number) => api.delete(`/api/reports/${id}/`),
  submit: (id: number) => api.post<WeeklyReport>(`/api/reports/${id}/submit/`),
  withdraw: (id: number) => api.post<WeeklyReport>(`/api/reports/${id}/withdraw/`),
  weekRecords: (week_start: string) => api.get<WeekRecords>('/api/reports/week-records/', { week_start }),
  upload: (id: number, file: File, onProgress?: (percent: number) => void) => {
    const form = new FormData()
    form.append('file', file)
    return uploadForm<ReportFile>(`/api/reports/${id}/files/`, form, onProgress)
  },
  removeFile: (fileId: number) => api.delete(`/api/report-files/${fileId}/`),
  feedback: (id: number, body: FeedbackWrite) => api.post<WeeklyReport>(`/api/reports/${id}/feedback/`, body),
  history: (id: number) => api.get<HistoryEntry[]>(`/api/reports/${id}/history/`),
  missing: (week_start?: string, signal?: AbortSignal) => api.get<UserBrief[]>('/api/reports/missing/', { week_start }, signal),
  remindMissing: (week_start: string) => api.post<{ reminded: number; already: number }>('/api/reports/remind-missing/', { week_start }),
  digest: (week_start?: string, signal?: AbortSignal) => api.get<WeeklyReportDigest>('/api/reports/digest/', { week_start }, signal),
  digestExportUrl: (week_start?: string) =>
    week_start ? `/api/reports/digest/export/?week_start=${encodeURIComponent(week_start)}` : '/api/reports/digest/export/',
}

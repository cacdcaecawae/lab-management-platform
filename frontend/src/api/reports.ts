import { api, type Page } from './client'
import type { FeedbackWrite, HistoryEntry, ListQuery, ReportWrite, UserBrief, WeeklyReport, WeeklyReportBrief } from './types'

export const reportsApi = {
  list: (q?: ListQuery) => api.get<Page<WeeklyReportBrief>>('/api/reports/', q),
  get: (id: number) => api.get<WeeklyReport>(`/api/reports/${id}/`),
  create: (body: ReportWrite) => api.post<WeeklyReport>('/api/reports/', body),
  update: (id: number, body: Partial<ReportWrite>) => api.patch<WeeklyReport>(`/api/reports/${id}/`, body),
  submit: (id: number) => api.post<WeeklyReport>(`/api/reports/${id}/submit/`),
  feedback: (id: number, body: FeedbackWrite) => api.post<WeeklyReport>(`/api/reports/${id}/feedback/`, body),
  history: (id: number) => api.get<HistoryEntry[]>(`/api/reports/${id}/history/`),
  missing: (week_start?: string) => api.get<UserBrief[]>('/api/reports/missing/', { week_start }),
}

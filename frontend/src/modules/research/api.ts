import { api, type Page } from '@/api/client'
import type { Experiment, ExperimentWrite, HistoryEntry, ListQuery, ProcessingRun, RunWrite } from '@/api/types'

// Experiments and processing runs share the same endpoint shape (api-contract.md).
function recordApi<T, W>(base: string) {
  return {
    list: (q?: ListQuery) => api.get<Page<T>>(base, q),
    get: (id: number) => api.get<T>(`${base}${id}/`),
    create: (body: W) => api.post<T>(base, body),
    update: (id: number, body: Partial<W>) => api.patch<T>(`${base}${id}/`, body),
    submit: (id: number) => api.post<T>(`${base}${id}/submit/`),
    returnToDraft: (id: number, reason: string) => api.post<T>(`${base}${id}/return/`, { reason }),
    history: (id: number) => api.get<HistoryEntry[]>(`${base}${id}/history/`),
  }
}

export const experimentsApi = recordApi<Experiment, ExperimentWrite>('/api/experiments/')
export const runsApi = recordApi<ProcessingRun, RunWrite>('/api/runs/')

import { api, type Page } from './client'
import type { ListQuery, Project, ProjectLog, ProjectWrite } from './types'

export const projectsApi = {
  list: (q?: ListQuery) => api.get<Page<Project>>('/api/projects/', q),
  get: (id: number) => api.get<Project>(`/api/projects/${id}/`),
  create: (body: ProjectWrite) => api.post<Project>('/api/projects/', body),
  update: (id: number, body: Partial<ProjectWrite>) => api.patch<Project>(`/api/projects/${id}/`, body),
  logs: (id: number, q?: ListQuery) => api.get<Page<ProjectLog>>(`/api/projects/${id}/logs/`, q),
  addLog: (id: number, body: { date: string; content: string }) => api.post<ProjectLog>(`/api/projects/${id}/logs/`, body),
}

import { api, type Page, type Query } from './client'
import type { ListQuery, MilestoneWrite, Project, ProjectLog, ProjectMilestone, ProjectTask, ProjectWrite, TaskWrite } from './types'

export const projectsApi = {
  list: (q?: ListQuery) => api.get<Page<Project>>('/api/projects/', q),
  get: (id: number) => api.get<Project>(`/api/projects/${id}/`),
  create: (body: ProjectWrite) => api.post<Project>('/api/projects/', body),
  update: (id: number, body: Partial<ProjectWrite>) => api.patch<Project>(`/api/projects/${id}/`, body),
  logs: (id: number, q?: ListQuery) => api.get<Page<ProjectLog>>(`/api/projects/${id}/logs/`, q),
  addLog: (id: number, body: { date: string; content: string }) => api.post<ProjectLog>(`/api/projects/${id}/logs/`, body),
  tasks: (id: number, q?: Query) => api.get<Page<ProjectTask>>(`/api/projects/${id}/tasks/`, q),
  addTask: (id: number, body: Partial<TaskWrite>) => api.post<ProjectTask>(`/api/projects/${id}/tasks/`, body),
  updateTask: (id: number, body: Partial<TaskWrite>) => api.patch<ProjectTask>(`/api/tasks/${id}/`, body),
  deleteTask: (id: number) => api.delete(`/api/tasks/${id}/`),
  milestones: (id: number, q?: Query) => api.get<Page<ProjectMilestone>>(`/api/projects/${id}/milestones/`, q),
  addMilestone: (id: number, body: MilestoneWrite) => api.post<ProjectMilestone>(`/api/projects/${id}/milestones/`, body),
  updateMilestone: (id: number, body: Partial<MilestoneWrite>) => api.patch<ProjectMilestone>(`/api/milestones/${id}/`, body),
  deleteMilestone: (id: number) => api.delete(`/api/milestones/${id}/`),
}

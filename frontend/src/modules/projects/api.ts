import { api, type Page, type Query } from '@/api/client'
import { uploadForm } from '@/modules/datasets/api'
import type {
  ListQuery, MilestoneWrite, Project, ProjectFile, ProjectLog, ProjectMilestone, ProjectTask, ProjectWrite, TaskWrite,
} from '@/api/types'

type LogWrite = { date: string; content: string }

export const projectsApi = {
  list: (q?: ListQuery) => api.get<Page<Project>>('/api/projects/', q),
  get: (id: number) => api.get<Project>(`/api/projects/${id}/`),
  create: (body: ProjectWrite) => api.post<Project>('/api/projects/', body),
  update: (id: number, body: Partial<ProjectWrite>) => api.patch<Project>(`/api/projects/${id}/`, body),
  logs: (id: number, q?: ListQuery) => api.get<Page<ProjectLog>>(`/api/projects/${id}/logs/`, q),
  addLog: (id: number, body: LogWrite) => api.post<ProjectLog>(`/api/projects/${id}/logs/`, body),
  updateLog: (logId: number, body: Partial<LogWrite>) => api.patch<ProjectLog>(`/api/project-logs/${logId}/`, body),
  removeLog: (logId: number) => api.delete(`/api/project-logs/${logId}/`),
  files: (id: number) => api.get<ProjectFile[]>(`/api/projects/${id}/files/`),
  upload: (id: number, file: File, onProgress?: (percent: number) => void) => {
    const form = new FormData()
    form.append('file', file)
    return uploadForm<ProjectFile>(`/api/projects/${id}/files/`, form, onProgress)
  },
  removeFile: (fileId: number) => api.delete(`/api/project-files/${fileId}/`),
  tasks: (id: number, q?: Query) => api.get<Page<ProjectTask>>(`/api/projects/${id}/tasks/`, q),
  addTask: (id: number, body: Partial<TaskWrite>) => api.post<ProjectTask>(`/api/projects/${id}/tasks/`, body),
  updateTask: (id: number, body: Partial<TaskWrite>) => api.patch<ProjectTask>(`/api/tasks/${id}/`, body),
  deleteTask: (id: number) => api.delete(`/api/tasks/${id}/`),
  milestones: (id: number, q?: Query) => api.get<Page<ProjectMilestone>>(`/api/projects/${id}/milestones/`, q),
  addMilestone: (id: number, body: MilestoneWrite) => api.post<ProjectMilestone>(`/api/projects/${id}/milestones/`, body),
  updateMilestone: (id: number, body: Partial<MilestoneWrite>) => api.patch<ProjectMilestone>(`/api/milestones/${id}/`, body),
  deleteMilestone: (id: number) => api.delete(`/api/milestones/${id}/`),
}

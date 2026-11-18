import { api, type Page } from './client'
import type { ListQuery, MemberCreate, MemberDetail, MemberListItem, MemberUpdate } from './types'

export const membersApi = {
  list: (q?: ListQuery) => api.get<Page<MemberListItem>>('/api/members/', q),
  create: (body: MemberCreate) => api.post<MemberDetail>('/api/members/', body),
  update: (id: number, body: MemberUpdate) => api.patch<MemberDetail>(`/api/members/${id}/`, body),
  resetPassword: (id: number, password: string) => api.post<void>(`/api/members/${id}/reset-password/`, { password }),
}

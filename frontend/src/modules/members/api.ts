import { api, type Page } from '@/api/client'
import type { ListQuery, MemberCreate, MemberDetail, MemberListItem, MemberUpdate, PendingMember } from '@/api/types'

export const membersApi = {
  list: (q?: ListQuery) => api.get<Page<MemberListItem>>('/api/members/', q),
  create: (body: MemberCreate) => api.post<MemberDetail>('/api/members/', body),
  update: (id: number, body: MemberUpdate) => api.patch<MemberDetail>(`/api/members/${id}/`, body),
  resetPassword: (id: number, password: string) => api.post<void>(`/api/members/${id}/reset-password/`, { password }),
  pending: () => api.get<PendingMember[]>('/api/members/pending/'),
  approve: (ids: number[]) => api.post<{ count: number }>('/api/members/approve/', { ids }),
  reject: (ids: number[]) => api.post<{ count: number }>('/api/members/reject/', { ids }),
  signup: () => api.get<{ code: string }>('/api/members/signup/'),
  setSignup: (open: boolean) => api.post<{ code: string }>('/api/members/signup/', { open }),
}

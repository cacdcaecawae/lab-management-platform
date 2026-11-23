import { api, withQuery, type Page } from '@/api/client'
import type { ListQuery, MemberCreate, MemberDetail, MemberListItem, MemberUpdate, PendingMember } from '@/api/types'

export const membersApi = {
  list: (q?: ListQuery) => api.get<Page<MemberListItem>>('/api/members/', q),
  create: (body: MemberCreate) => api.post<MemberDetail>('/api/members/', body),
  update: (id: number, body: MemberUpdate) => api.patch<MemberDetail>(`/api/members/${id}/`, body),
  resetPassword: (id: number, password: string) => api.post<void>(`/api/members/${id}/reset-password/`, { password }),
  // 终审人: give or take back the 管理员 tag
  setManager: (id: number, on: boolean) => api.post<MemberDetail>(`/api/members/${id}/manager/`, { is_manager: on }),
  // 花名册 .xlsx with the list's filters (advisors and managers)
  exportUrl: (q: ListQuery) => withQuery('/api/members/export/', q),
  pending: () => api.get<PendingMember[]>('/api/members/pending/'),
  approve: (ids: number[]) => api.post<{ count: number }>('/api/members/approve/', { ids }),
  reject: (ids: number[]) => api.post<{ count: number }>('/api/members/reject/', { ids }),
  signup: () => api.get<{ code: string }>('/api/members/signup/'),
  setSignup: (open: boolean) => api.post<{ code: string }>('/api/members/signup/', { open }),
}

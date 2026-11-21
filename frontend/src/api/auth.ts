import { api } from './client'
import type { Me, MeUpdate, Registration } from './types'

export const authApi = {
  csrf: () => api.get<void>('/api/auth/csrf/'),
  login: (username: string, password: string) => api.post<Me>('/api/auth/login/', { username, password }),
  logout: () => api.post<void>('/api/auth/logout/'),
  me: () => api.get<Me>('/api/auth/me/'),
  updateMe: (body: MeUpdate) => api.patch<Me>('/api/auth/me/', body),
  uploadAvatar: (picture: Blob) => {
    const form = new FormData()
    form.append('file', picture, 'avatar.jpg')
    return api.post<Me>('/api/auth/me/avatar/', form)
  },
  changePassword: (old_password: string, new_password: string) =>
    api.post<void>('/api/auth/password/', { old_password, new_password }),
  register: (body: Registration) => api.post<void>('/api/auth/register/', body),
}

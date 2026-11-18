import { api } from './client'
import type { Me } from './types'

export const authApi = {
  csrf: () => api.get<void>('/api/auth/csrf/'),
  login: (username: string, password: string) => api.post<Me>('/api/auth/login/', { username, password }),
  logout: () => api.post<void>('/api/auth/logout/'),
  me: () => api.get<Me>('/api/auth/me/'),
  changePassword: (old_password: string, new_password: string) =>
    api.post<void>('/api/auth/password/', { old_password, new_password }),
}

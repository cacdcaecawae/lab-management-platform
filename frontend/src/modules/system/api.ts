import { api, type Page } from '@/api/client'
import type {
  Account,
  AccountCreate,
  AccountUpdate,
  HistoryEntry,
  ListQuery,
  MailSettings,
  MailSettingsWrite,
  SystemGroup,
  SystemGroupWrite,
  VersionInfo,
} from '@/api/types'

export type OpsRun = { finished_at: string; ok: boolean; snapshot: string; detail: string }
export type StorageInfo = {
  primary: 'nas' | 'local'
  nas_ready: boolean | null
  backup: { last_ok: OpsRun | null; last_failure: OpsRun | null; overdue: boolean; failing: boolean }
  drill: { last: OpsRun | null; overdue: boolean }
  attention: boolean
}

export const systemApi = {
  storage: () => api.get<StorageInfo>('/api/system/storage-status/'),
  mail: () => api.get<MailSettings>('/api/system/mail/'),
  saveMail: (body: MailSettingsWrite) => api.put<MailSettings>('/api/system/mail/', body),
  mailHistory: () => api.get<HistoryEntry[]>('/api/system/mail/history/'),
  testMail: (to: string) => api.post<{ to: string }>('/api/system/mail/test/', { to }),
  version: () => api.get<VersionInfo>('/api/system/version/'),
  groups: (q?: ListQuery) => api.get<Page<SystemGroup>>('/api/system/groups/', q),
  createGroup: (body: SystemGroupWrite) => api.post<SystemGroup>('/api/system/groups/', body),
  updateGroup: (id: number, body: SystemGroupWrite) => api.patch<SystemGroup>(`/api/system/groups/${id}/`, body),
  accounts: (q?: ListQuery) => api.get<Page<Account>>('/api/system/accounts/', q),
  createAccount: (body: AccountCreate) => api.post<Account>('/api/system/accounts/', body),
  updateAccount: (id: number, body: AccountUpdate) => api.patch<Account>(`/api/system/accounts/${id}/`, body),
  resetPassword: (id: number, password: string) => api.post<void>(`/api/system/accounts/${id}/reset-password/`, { password }),
}

import { api, type Page, type Query } from '@/api/client'

export type LoginOutcome = 'success' | 'failed' | 'throttled'
export interface LoginEvent {
  id: number
  at: string
  outcome: LoginOutcome
  account: { id: number; username: string } | null
  ip: string | null
}
export interface LoginEventPage extends Page<LoginEvent> {
  audit_enabled: boolean
  top_failed_24h: Array<{ user_id: number; user__username: string; failures: number }>
}
export const loginEventsApi = {
  list: (query: Query) => api.get<LoginEventPage>('/api/system/logins/', query),
}

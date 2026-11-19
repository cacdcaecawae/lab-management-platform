import { api } from '@/api/client'

export interface Usage {
  known_bytes: number
  unknown_files: number
}
export interface UsageGroup extends Usage {
  id: number | null
  name: string
  modules: Record<string, Usage>
  months: Record<string, number>
}
export interface OpsStorage {
  disk: { kind: 'local' | 'non_local'; filesystem: { total_bytes: number; used_bytes: number; free_bytes: number } | null }
  groups: UsageGroup[]
  month_keys: string[]
  projection: { basis_months: string[]; annual_retained_known_bytes: number } | null
}
export interface GroupStorage {
  by_member: Array<Usage & { id: number | null; label: string }>
  by_project: Array<Usage & { id: number | null; label: string }>
}
export const storageApi = {
  ops: () => api.get<OpsStorage>('/api/system/storage/'),
  group: () => api.get<GroupStorage>('/api/storage-usage/'),
}

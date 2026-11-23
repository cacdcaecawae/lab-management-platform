import { api } from '@/api/client'
import type { VersionInfo } from '@/api/types'

// The two checks the ops sidebar marks (stores/ops). Shared code may not import src/modules
// (scripts/check_module_deps.py), so they live here; modules/system/api.ts includes them in systemApi.
export type OpsRun = { finished_at: string; ok: boolean; snapshot: string; detail: string }
export type StorageInfo = {
  primary: 'nas' | 'local'
  nas_ready: boolean | null
  disk_free: number | null
  disk_low: boolean
  backup: { last_ok: OpsRun | null; last_failure: OpsRun | null; overdue: boolean; failing: boolean }
  drill: { last: OpsRun | null; overdue: boolean }
  attention: boolean
}

export const opsStatusApi = {
  storage: () => api.get<StorageInfo>('/api/system/storage-status/'),
  version: (refresh = false) => api.get<VersionInfo>('/api/system/version/', { refresh: refresh ? 1 : undefined }),
}

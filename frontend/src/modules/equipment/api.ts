import { api, withQuery, type Page } from '@/api/client'
import type {
  Booking,
  BookingWrite,
  Condition,
  Equipment,
  EquipmentDetail,
  EquipmentStatus,
  EquipmentWrite,
  HistoryEntry,
  ListQuery,
} from '@/api/types'

export const equipmentApi = {
  list: (q?: ListQuery) => api.get<Page<Equipment>>('/api/equipment/', q),
  get: (id: number) => api.get<EquipmentDetail>(`/api/equipment/${id}/`),
  create: (body: EquipmentWrite) => api.post<Equipment>('/api/equipment/', body),
  // status_seen: the status the form showed when it opened; required with a status change (409 stale_status if it moved).
  update: (id: number, body: Partial<EquipmentWrite> & { status_seen?: EquipmentStatus }) =>
    api.patch<Equipment>(`/api/equipment/${id}/`, body),
  history: (id: number) => api.get<HistoryEntry[]>(`/api/equipment/${id}/history/`),
}

export const bookingsApi = {
  // Not paginated: every uncancelled booking overlapping [from, to) (at most 62 days).
  list: (q: { from: string; to: string; equipment?: number | ''; mine?: 1 | '' }) => api.get<Booking[]>('/api/bookings/', q),
  get: (id: number) => api.get<Booking>(`/api/bookings/${id}/`),
  create: (body: BookingWrite) => api.post<Booking>('/api/bookings/', body),
  cancel: (id: number) => api.post<Booking>(`/api/bookings/${id}/cancel/`),
  report: (id: number, body: { condition: Condition; description: string; photo?: File | null }) => {
    const form = new FormData()
    form.append('condition', body.condition)
    form.append('description', body.description)
    if (body.photo) form.append('photo', body.photo)
    return api.post<Booking>(`/api/bookings/${id}/report/`, form)
  },
}

export type UsageDimension = 'equipment' | 'user' | 'project' | 'month'
export interface UsageStatsQuery {
  from: string
  to: string
  by: UsageDimension
}
export interface UsageStatsRow {
  key: { id: number | string | null; label: string }
  booked_hours: number
  reported_hours: number
  bookings: number
  abnormal: number
}
export const usageStatsApi = {
  list: (q: UsageStatsQuery) => api.get<UsageStatsRow[]>('/api/equipment/usage-stats/', { ...q }),
  exportUrl: (q: UsageStatsQuery) => withQuery('/api/equipment/usage-stats/export/', { ...q }),
}

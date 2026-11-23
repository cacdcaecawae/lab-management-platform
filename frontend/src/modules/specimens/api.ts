import { api, type Page } from '@/api/client'
import type { HistoryEntry, ListQuery, LoanWrite, Specimen, SpecimenLoan, SpecimenWrite } from '@/api/types'

export const specimensApi = {
  // q: search, kind, status, on_loan=1, overdue=1, mine=1 (borrowed by me and not returned)
  list: (q?: ListQuery) => api.get<Page<Specimen>>('/api/specimens/', q),
  get: (id: number) => api.get<Specimen>(`/api/specimens/${id}/`),
  create: (body: SpecimenWrite) => api.post<Specimen>('/api/specimens/', body),
  update: (id: number, body: Partial<SpecimenWrite>) => api.patch<Specimen>(`/api/specimens/${id}/`, body),
  history: (id: number) => api.get<HistoryEntry[]>(`/api/specimens/${id}/history/`),
  loans: (id: number, q?: ListQuery) => api.get<Page<SpecimenLoan>>(`/api/specimens/${id}/loans/`, q),
  borrow: (id: number, body: LoanWrite) => api.post<SpecimenLoan>(`/api/specimens/${id}/borrow/`, body),
  giveBack: (
    id: number,
    loanIdSeen: number,
    payload: string | { note?: string; return_location?: string; photo?: File | null } = '',
  ) => {
    const opts = typeof payload === 'string' ? { note: payload } : payload
    if (opts.photo) {
      const form = new FormData()
      form.append('loan_id_seen', String(loanIdSeen))
      if (opts.note) form.append('note', opts.note)
      if (opts.return_location) form.append('return_location', opts.return_location)
      form.append('photo', opts.photo)
      return api.post<SpecimenLoan>(`/api/specimens/${id}/return/`, form)
    }
    const body: Record<string, unknown> = { loan_id_seen: loanIdSeen, note: opts.note ?? '' }
    if (opts.return_location) body.return_location = opts.return_location
    return api.post<SpecimenLoan>(`/api/specimens/${id}/return/`, body)
  },
}

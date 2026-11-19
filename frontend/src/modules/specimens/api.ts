import { api, type Page } from '@/api/client'
import type { HistoryEntry, ListQuery, LoanWrite, Specimen, SpecimenLoan, SpecimenWrite } from '@/api/types'

export const specimensApi = {
  // q: search, kind, status, on_loan=1, mine=1 (borrowed by me and not returned)
  list: (q?: ListQuery) => api.get<Page<Specimen>>('/api/specimens/', q),
  get: (id: number) => api.get<Specimen>(`/api/specimens/${id}/`),
  create: (body: SpecimenWrite) => api.post<Specimen>('/api/specimens/', body),
  update: (id: number, body: Partial<SpecimenWrite>) => api.patch<Specimen>(`/api/specimens/${id}/`, body),
  history: (id: number) => api.get<HistoryEntry[]>(`/api/specimens/${id}/history/`),
  loans: (id: number, q?: ListQuery) => api.get<Page<SpecimenLoan>>(`/api/specimens/${id}/loans/`, q),
  borrow: (id: number, body: LoanWrite) => api.post<SpecimenLoan>(`/api/specimens/${id}/borrow/`, body),
  giveBack: (id: number, loanIdSeen: number, note: string) => api.post<SpecimenLoan>(`/api/specimens/${id}/return/`, { loan_id_seen: loanIdSeen, note }),
}

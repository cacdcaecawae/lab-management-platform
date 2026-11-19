import { api, withQuery, type Page } from '@/api/client'
import type {
  Attachment,
  AttachmentKind,
  Fund,
  FundWrite,
  HistoryEntry,
  ListQuery,
  Purchase,
  PurchaseDetail,
  PurchaseWrite,
  Reimbursement,
  ReimbursementStats,
  ReimbursementStatus,
  ReimbursementWrite,
  ReviewWrite,
} from '@/api/types'

function upload(path: string, file: File, kind: AttachmentKind) {
  const form = new FormData()
  form.append('file', file)
  form.append('kind', kind)
  return api.post<Attachment>(path, form)
}

export const fundsApi = {
  list: (q?: ListQuery) => api.get<Page<Fund>>('/api/funds/', q),
  create: (body: FundWrite) => api.post<Fund>('/api/funds/', body),
  update: (id: number, body: Partial<FundWrite>) => api.patch<Fund>(`/api/funds/${id}/`, body),
}

export const purchasesApi = {
  // q: status, mine=1, todo=1 (waiting for my review), search
  list: (q?: ListQuery) => api.get<Page<Purchase>>('/api/purchases/', q),
  get: (id: number) => api.get<PurchaseDetail>(`/api/purchases/${id}/`),
  create: (body: PurchaseWrite) => api.post<PurchaseDetail>('/api/purchases/', body),
  update: (id: number, body: Partial<PurchaseWrite>) => api.patch<PurchaseDetail>(`/api/purchases/${id}/`, body),
  remove: (id: number) => api.delete(`/api/purchases/${id}/`),
  submit: (id: number) => api.post<PurchaseDetail>(`/api/purchases/${id}/submit/`),
  withdraw: (id: number) => api.post<PurchaseDetail>(`/api/purchases/${id}/withdraw/`),
  review: (id: number, body: ReviewWrite) => api.post<PurchaseDetail>(`/api/purchases/${id}/review/`, body),
  markPurchased: (id: number) => api.post<PurchaseDetail>(`/api/purchases/${id}/purchased/`),
  markArrived: (id: number) => api.post<PurchaseDetail>(`/api/purchases/${id}/arrived/`),
  upload: (id: number, file: File, kind: AttachmentKind) => upload(`/api/purchases/${id}/attachments/`, file, kind),
  history: (id: number) => api.get<HistoryEntry[]>(`/api/purchases/${id}/history/`),
}

export const attachmentsApi = {
  remove: (id: number) => api.delete(`/api/attachments/${id}/`),
}

export const reimbursementsApi = {
  // q: status, category, fund, owner, month (YYYY-MM), from / to (YYYY-MM-DD); stats and export take the same filters
  list: (q?: ListQuery) => api.get<Page<Reimbursement>>('/api/reimbursements/', q),
  get: (id: number) => api.get<Reimbursement>(`/api/reimbursements/${id}/`),
  create: (body: ReimbursementWrite) => api.post<Reimbursement>('/api/reimbursements/', body),
  update: (id: number, body: Partial<ReimbursementWrite>) => api.patch<Reimbursement>(`/api/reimbursements/${id}/`, body),
  remove: (id: number) => api.delete(`/api/reimbursements/${id}/`),
  advance: (id: number, status: ReimbursementStatus) => api.post<Reimbursement>(`/api/reimbursements/${id}/advance/`, { status }),
  upload: (id: number, file: File, kind: AttachmentKind) => upload(`/api/reimbursements/${id}/attachments/`, file, kind),
  history: (id: number) => api.get<HistoryEntry[]>(`/api/reimbursements/${id}/history/`),
  stats: (q: ListQuery) => api.get<ReimbursementStats>('/api/reimbursements/stats/', q),
  // a plain link: the browser downloads the .xlsx with the session cookie
  exportUrl: (q: ListQuery) => withQuery('/api/reimbursements/export/', q),
  remindFinance: () => api.post<{ sent: number; to: string }>('/api/reimbursements/remind-finance/'),
  financeEmail: () => api.get<{ finance_email: string }>('/api/reimbursements/finance-email/'),
  setFinanceEmail: (finance_email: string) =>
    api.patch<{ finance_email: string }>('/api/reimbursements/finance-email/', { finance_email }),
}

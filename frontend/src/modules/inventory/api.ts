import { api, withQuery, type Page } from '@/api/client'
import type { BatchModeWrite, Consumable, ConsumableWrite, LedgerTxn, ListQuery, StockTxn, StockTxnWrite } from '@/api/types'

export const consumablesApi = {
  list: (q?: ListQuery) => api.get<Page<Consumable>>('/api/consumables/', q),
  create: (body: ConsumableWrite) => api.post<Consumable>('/api/consumables/', body),
  update: (id: number, body: Partial<ConsumableWrite>) => api.patch<Consumable>(`/api/consumables/${id}/`, body),
  setBatchMode: (id: number, body: BatchModeWrite) => api.post<Consumable>(`/api/consumables/${id}/batch-mode/`, body),
  txns: (id: number, q?: ListQuery) => api.get<Page<StockTxn>>(`/api/consumables/${id}/txns/`, q),
  addTxn: (id: number, body: StockTxnWrite) => api.post<StockTxn>(`/api/consumables/${id}/txns/`, body),
  // the group ledger across consumables (advisors and managers: all; others: what they handled); same filters export
  ledger: (q?: ListQuery) => api.get<Page<LedgerTxn>>('/api/stock-txns/', q),
  ledgerExportUrl: (q: ListQuery) => withQuery('/api/stock-txns/export/', q),
}

import { api, type Page } from './client'
import type { Consumable, ConsumableWrite, ListQuery, StockTxn, StockTxnWrite } from './types'

export const consumablesApi = {
  list: (q?: ListQuery) => api.get<Page<Consumable>>('/api/consumables/', q),
  create: (body: ConsumableWrite) => api.post<Consumable>('/api/consumables/', body),
  update: (id: number, body: Partial<ConsumableWrite>) => api.patch<Consumable>(`/api/consumables/${id}/`, body),
  txns: (id: number, q?: ListQuery) => api.get<Page<StockTxn>>(`/api/consumables/${id}/txns/`, q),
  addTxn: (id: number, body: StockTxnWrite) => api.post<StockTxn>(`/api/consumables/${id}/txns/`, body),
}

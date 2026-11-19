import { api } from './client'

export interface SearchResult {
  id: number
  title: string
  subtitle: string
  link: string
}

export interface SearchGroup {
  module: string
  label: string
  items: SearchResult[]
}

export const searchSite = (q: string) => api.get<SearchGroup[]>('/api/search/', { q })

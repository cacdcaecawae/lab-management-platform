import { ref } from 'vue'
import { api } from './client'

// Values the group already uses in a free-text field, most used first (backend workbench/suggestions.py). They only
// suggest: a new spelling is still saved.
export type SuggestionField =
  | 'equipment.category'
  | 'equipment.location'
  | 'specimen.material'
  | 'specimen.location'
  | 'consumable.category'
  | 'consumable.location'
  | 'consumable.unit'
  | 'member.research_direction'
  | 'achievement.venue'
  | 'doc.tags'

export const suggestions = (field: SuggestionField, search = '') => api.get<string[]>(`/api/suggestions/${field}/`, { search })

// <el-autocomplete :fetch-suggestions="suggest('equipment.location')">
export const suggest = (field: SuggestionField) => (query: string, done: (items: { value: string }[]) => void) => {
  suggestions(field, query).then(
    (values) => done(values.map((value) => ({ value }))),
    () => done([]),
  )
}

// The values of a filter dropdown (<el-select filterable remote :remote-method="search">).
export function useSuggestions(field: SuggestionField) {
  const values = ref<string[]>([])
  const search = (text = '') => suggestions(field, text).then((v) => (values.value = v), () => undefined)
  search()
  return { values, search }
}

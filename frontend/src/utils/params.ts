// Key/value rows <-> the JSON object stored in `params`.

export interface ParamRow {
  key: string
  value: string
  original?: unknown
}

export function toRows(obj: Record<string, unknown> | null | undefined): ParamRow[] {
  return Object.entries(obj ?? {}).map(([key, v]) => ({ key, value: typeof v === 'string' ? v : JSON.stringify(v), original: v }))
}

// New values are strings; a non-string value from the API is kept as-is unless its text was edited.
export function toObject(rows: ParamRow[]): Record<string, unknown> {
  const out: Record<string, unknown> = {}
  for (const r of rows) {
    const key = r.key.trim()
    if (!key) continue
    const unchanged = r.original !== undefined && typeof r.original !== 'string' && r.value === JSON.stringify(r.original)
    out[key] = unchanged ? r.original : r.value
  }
  return out
}

export function paramsProblem(rows: ParamRow[]): string {
  if (rows.some((r) => !r.key.trim() && r.value.trim())) return '有参数值没有填写参数名'
  const keys = rows.map((r) => r.key.trim()).filter(Boolean)
  const dup = keys.find((k, i) => keys.indexOf(k) !== i)
  return dup ? `参数名重复：${dup}` : ''
}

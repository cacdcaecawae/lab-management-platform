import { computed, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { ApiError } from '@/api/client'

export const isNotFound = (e: unknown) => e instanceof ApiError && e.status === 404

export function errorMessage(e: unknown): string {
  if (isNotFound(e)) return '记录不存在或无权查看'
  if (e instanceof ApiError) return e.message
  return '网络错误，请稍后重试' // fetch rejects with TypeError when the request never got a response
}

export function showError(e: unknown) {
  if (!(e instanceof ApiError)) console.error(e)
  ElMessage.error(errorMessage(e))
}

// Nested serializers answer with objects, e.g. items: {"1": {"link": [...]}}, not a list of strings: flatten them.
const flatten = (v: unknown): string[] =>
  Array.isArray(v) ? v.flatMap(flatten) : v && typeof v === 'object' ? Object.values(v).flatMap(flatten) : [String(v)]

// For a button with no form to put field errors in: show what the server said
// ("交财务前请先上传发票"), not the generic "提交的数据有误".
export function showActionError(e: unknown) {
  if (e instanceof ApiError && e.body.errors) ElMessage.error(Object.values(normalizeErrors(e.body.errors, [])).flat().join('；'))
  else showError(e)
}

// Map backend error keys onto the form's field names: `project` -> `project_id`, `inputs` -> `input_ids`.
export function normalizeErrors(errors: Record<string, unknown>, known: string[]): Record<string, string[]> {
  const out: Record<string, string[]> = {}
  for (const [k, msgs] of Object.entries(errors)) {
    const key = [k, `${k}_id`, `${k.replace(/s$/, '')}_ids`].find((c) => known.includes(c)) ?? k
    out[key] = [...(out[key] ?? []), ...flatten(msgs)]
  }
  return out
}

// Field errors for <el-form-item :error="fe('title')">; anything the form has no item for goes to `others`.
// conflictField: the field a 409 belongs to (a login name already taken), so it shows under that field too.
export function useFieldErrors(known: string[], conflictField?: string) {
  const errors = ref<Record<string, string[]>>({})
  const fe = (field: string) => errors.value[field]?.join('；')
  const others = computed(() =>
    Object.entries(errors.value)
      .filter(([k]) => !known.includes(k))
      .map(([k, msgs]) => (k === 'non_field_errors' ? msgs.join('；') : `${k}：${msgs.join('；')}`)),
  )
  function handle(e: unknown) {
    if (conflictField && e instanceof ApiError && e.status === 409) errors.value = { [conflictField]: [e.message] }
    else errors.value = e instanceof ApiError && e.body.errors ? normalizeErrors(e.body.errors, known) : {}
    showError(e)
  }
  const clear = () => (errors.value = {})
  return { fe, others, handle, clear }
}

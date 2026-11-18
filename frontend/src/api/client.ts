// Thin fetch wrapper. Session cookie auth: same origin, cookies sent automatically;
// unsafe methods carry the csrftoken cookie in X-CSRFToken (Django CSRF protection).

export interface ApiErrorBody {
  code: string
  message: string
  // usually a list of messages per field; nested serializers send objects instead (see normalizeErrors)
  errors?: Record<string, string[]>
}

export class ApiError extends Error {
  constructor(
    public status: number,
    public body: ApiErrorBody,
  ) {
    super(body.message)
  }
}

export interface Page<T> {
  count: number
  next: string | null
  previous: string | null
  results: T[]
}

export type Query = Record<string, string | number | boolean | undefined | null>

// Set by the router: called when the session expired or the initial password must be changed.
export const authRequired: { handler?: (code: string) => void } = {}

// Exported for XMLHttpRequest uploads (fetch cannot report upload progress).
export function csrfToken(): string {
  return document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/)?.[1] ?? ''
}

export function withQuery(path: string, query?: Query): string {
  if (!query) return path
  const params = new URLSearchParams()
  for (const [k, v] of Object.entries(query)) if (v !== undefined && v !== null && v !== '') params.set(k, String(v))
  const qs = params.toString()
  return qs ? `${path}?${qs}` : path
}

async function request<T>(method: string, path: string, body?: unknown, query?: Query): Promise<T> {
  const headers: Record<string, string> = { Accept: 'application/json' }
  let payload: BodyInit | undefined
  if (body instanceof FormData) payload = body
  else if (body !== undefined) {
    headers['Content-Type'] = 'application/json'
    payload = JSON.stringify(body)
  }
  if (method !== 'GET') headers['X-CSRFToken'] = csrfToken()
  const res = await fetch(withQuery(path, query), { method, headers, body: payload, credentials: 'same-origin' })
  if (res.status === 204) return undefined as T
  const data = await res.json().catch(() => null)
  if (!res.ok) {
    // Non-JSON errors come from Nginx (e.g. 429 login rate limit, 413 body too large).
    const message = res.status === 429 ? '尝试次数过多，请一分钟后再试' : `请求失败（${res.status}）`
    const fallback: ApiErrorBody = { code: `http_${res.status}`, message }
    const error = new ApiError(res.status, data && typeof data.code === 'string' ? data : fallback)
    // /me/ is how the auth store asks "am I logged in?", so its 403 is an answer, not an expiry.
    const authCodes = ['not_authenticated', 'password_change_required']
    if (res.status === 403 && authCodes.includes(error.body.code) && path !== '/api/auth/me/') {
      authRequired.handler?.(error.body.code)
    }
    throw error
  }
  return data as T
}

export const api = {
  get: <T>(path: string, query?: Query) => request<T>('GET', path, undefined, query),
  post: <T>(path: string, body?: unknown) => request<T>('POST', path, body),
  put: <T>(path: string, body: unknown) => request<T>('PUT', path, body),
  patch: <T>(path: string, body: unknown) => request<T>('PATCH', path, body),
  delete: (path: string) => request<void>('DELETE', path),
}

import { afterEach, describe, expect, it, vi } from 'vitest'
import { api, ApiError, withQuery } from './client'

afterEach(() => vi.unstubAllGlobals())

function stubFetch(status: number, body: unknown) {
  const fetchMock = vi.fn().mockResolvedValue(new Response(body === null ? null : JSON.stringify(body), { status }))
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

describe('api client', () => {
  it('drops empty query values', () => {
    expect(withQuery('/api/x/', { a: 1, b: '', c: undefined, d: null, e: 'y' })).toBe('/api/x/?a=1&e=y')
  })

  it('sends the csrf cookie on unsafe requests', async () => {
    document.cookie = 'csrftoken=abc123'
    const fetchMock = stubFetch(200, { ok: true })
    await api.post('/api/x/', { a: 1 })
    const init = fetchMock.mock.calls[0][1]
    expect(init.headers['X-CSRFToken']).toBe('abc123')
    expect(init.body).toBe('{"a":1}')
  })

  it('throws ApiError with the uniform error body', async () => {
    stubFetch(400, { code: 'validation_error', message: '提交的数据有误', errors: { name: ['必填'] } })
    const err = (await api.get('/api/x/').catch((e) => e)) as ApiError
    expect(err).toBeInstanceOf(ApiError)
    expect(err.status).toBe(400)
    expect(err.body.errors?.name).toEqual(['必填'])
  })

  it('returns undefined for 204', async () => {
    stubFetch(204, null)
    await expect(api.delete('/api/x/1/')).resolves.toBeUndefined()
  })
})

describe('auth expiry', () => {
  it('calls the auth handler for expired sessions but not for /me/', async () => {
    const { authRequired } = await import('./client')
    const handler = vi.fn()
    authRequired.handler = handler
    stubFetch(403, { code: 'not_authenticated', message: '未登录' })
    await api.get('/api/projects/').catch(() => {})
    expect(handler).toHaveBeenCalledWith('not_authenticated')
    handler.mockClear()
    stubFetch(403, { code: 'not_authenticated', message: '未登录' })
    await api.get('/api/auth/me/').catch(() => {})
    expect(handler).not.toHaveBeenCalled()
    authRequired.handler = undefined
  })
})

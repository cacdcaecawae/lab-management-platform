// URL / method / body of every API module call, checked against docs/api-contract.md.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { datasetsApi } from './api'

let fetchMock: ReturnType<typeof vi.fn>

beforeEach(() => {
  fetchMock = vi.fn().mockImplementation(() => Promise.resolve(new Response('{}', { status: 200 })))
  vi.stubGlobal('fetch', fetchMock)
})
afterEach(() => vi.unstubAllGlobals())

function lastCall() {
  const [url, init] = fetchMock.mock.calls.at(-1)!
  return { url, method: init.method, body: init.body === undefined ? undefined : JSON.parse(init.body) }
}

describe('datasets', () => {
  it('covers list, detail, create and files', async () => {
    await datasetsApi.list({ project: 2, kind: 'script', owner: 7 })
    expect(lastCall()).toMatchObject({ url: '/api/datasets/?project=2&kind=script&owner=7', method: 'GET' })
    await datasetsApi.get(9)
    expect(lastCall()).toMatchObject({ url: '/api/datasets/9/', method: 'GET' })
    const body = { project_id: 2, name: 'D', kind: 'raw' as const, description: '' }
    await datasetsApi.create(body)
    expect(lastCall()).toEqual({ url: '/api/datasets/', method: 'POST', body })
    await datasetsApi.files(9)
    expect(lastCall()).toMatchObject({ url: '/api/datasets/9/files/', method: 'GET' })
  })
})

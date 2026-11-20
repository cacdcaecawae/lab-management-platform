// URL / method / body of every API module call, checked against docs/api-contract.md.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { consumablesApi } from './api'

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

describe('consumables', () => {
  it('posts stock transactions', async () => {
    const body = { kind: 'out' as const, quantity: 2, project_id: null, note: '' }
    await consumablesApi.addTxn(7, body)
    expect(lastCall()).toEqual({ url: '/api/consumables/7/txns/', method: 'POST', body })
  })
})

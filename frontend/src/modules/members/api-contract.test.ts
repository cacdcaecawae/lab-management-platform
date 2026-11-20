// URL / method / body of every API module call, checked against docs/api-contract.md.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { membersApi } from './api'

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

describe('members', () => {
  it('lists with filters', async () => {
    await membersApi.list({ search: '陈', role: 'student', is_active: true })
    expect(lastCall()).toEqual({ url: '/api/members/?search=%E9%99%88&role=student&is_active=true', method: 'GET', body: undefined })
  })
  it('creates, updates, resets password', async () => {
    const body = { username: 's1', name: '陈同学', role: 'student' as const, password: 'Init#2026x' }
    await membersApi.create(body)
    expect(lastCall()).toEqual({ url: '/api/members/', method: 'POST', body })
    await membersApi.update(3, { is_active: false })
    expect(lastCall()).toEqual({ url: '/api/members/3/', method: 'PATCH', body: { is_active: false } })
    await membersApi.resetPassword(3, 'New#2026x')
    expect(lastCall()).toEqual({ url: '/api/members/3/reset-password/', method: 'POST', body: { password: 'New#2026x' } })
  })
})

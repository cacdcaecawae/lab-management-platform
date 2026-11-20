// URL / method / body of every API module call, checked against docs/api-contract.md.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { projectsApi } from './api'

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

describe('projects', () => {
  it('covers list, detail, write and logs', async () => {
    await projectsApi.list({ status: 'active', mine: 1, search: '' })
    expect(lastCall()).toMatchObject({ url: '/api/projects/?status=active&mine=1', method: 'GET' })
    await projectsApi.get(5)
    expect(lastCall()).toMatchObject({ url: '/api/projects/5/', method: 'GET' })
    const body = { name: 'P', leader_id: 1, member_ids: [1, 2], stage: '', status: 'active' as const, description: '' }
    await projectsApi.create(body)
    expect(lastCall()).toEqual({ url: '/api/projects/', method: 'POST', body })
    await projectsApi.update(5, { stage: '试验' })
    expect(lastCall()).toEqual({ url: '/api/projects/5/', method: 'PATCH', body: { stage: '试验' } })
    await projectsApi.logs(5, { page: 2 })
    expect(lastCall()).toMatchObject({ url: '/api/projects/5/logs/?page=2', method: 'GET' })
    await projectsApi.addLog(5, { date: '2026-11-16', content: '完成' })
    expect(lastCall()).toEqual({ url: '/api/projects/5/logs/', method: 'POST', body: { date: '2026-11-16', content: '完成' } })
  })
})

// URL / method / body of every API module call, checked against docs/api-contract.md.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { reportsApi } from './api'

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

describe('reports', () => {
  it('covers report endpoints', async () => {
    await reportsApi.list({ status: 'submitted' })
    expect(lastCall()).toMatchObject({ url: '/api/reports/?status=submitted', method: 'GET' })
    await reportsApi.get(8)
    expect(lastCall()).toMatchObject({ url: '/api/reports/8/', method: 'GET' })
    const body = {
      week_start: '2026-11-16', goals: 'g', done: 'd', findings: 'f', next_plan: 'n',
      experiment_ids: [1], dataset_ids: [2], run_ids: [3],
    }
    await reportsApi.create(body)
    expect(lastCall()).toEqual({ url: '/api/reports/', method: 'POST', body })
    await reportsApi.update(8, { goals: 'g2' })
    expect(lastCall()).toEqual({ url: '/api/reports/8/', method: 'PATCH', body: { goals: 'g2' } })
    await reportsApi.remove(8)
    expect(lastCall()).toMatchObject({ url: '/api/reports/8/', method: 'DELETE' })
    await reportsApi.submit(8)
    expect(lastCall()).toMatchObject({ url: '/api/reports/8/submit/', method: 'POST' })
    await reportsApi.feedback(8, { verdict: 'needs_revision', content: '补充数据' })
    expect(lastCall()).toEqual({
      url: '/api/reports/8/feedback/', method: 'POST', body: { verdict: 'needs_revision', content: '补充数据' },
    })
    await reportsApi.history(8)
    expect(lastCall()).toMatchObject({ url: '/api/reports/8/history/', method: 'GET' })
    await reportsApi.missing('2026-11-09')
    expect(lastCall()).toMatchObject({ url: '/api/reports/missing/?week_start=2026-11-09', method: 'GET' })
    await reportsApi.missing()
    expect(lastCall()).toMatchObject({ url: '/api/reports/missing/', method: 'GET' })
    await reportsApi.digest('2026-11-16')
    expect(lastCall()).toMatchObject({ url: '/api/reports/digest/?week_start=2026-11-16', method: 'GET' })
    expect(reportsApi.digestExportUrl('2026-11-16')).toBe('/api/reports/digest/export/?week_start=2026-11-16')
  })
})

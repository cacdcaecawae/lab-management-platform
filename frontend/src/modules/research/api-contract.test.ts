// URL / method / body of every API module call, checked against docs/api-contract.md.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { experimentsApi, runsApi } from './api'

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

describe.each([
  ['experiments', experimentsApi],
  ['runs', runsApi],
] as const)('%s', (name, mod) => {
  it('covers the record endpoints', async () => {
    await mod.list({ project: 1, status: 'draft' })
    expect(lastCall()).toMatchObject({ url: `/api/${name}/?project=1&status=draft`, method: 'GET' })
    await mod.get(4)
    expect(lastCall()).toMatchObject({ url: `/api/${name}/4/`, method: 'GET' })
    await mod.create({ title: 'T' } as never)
    expect(lastCall()).toEqual({ url: `/api/${name}/`, method: 'POST', body: { title: 'T' } })
    await mod.update(4, { title: 'T2' })
    expect(lastCall()).toEqual({ url: `/api/${name}/4/`, method: 'PATCH', body: { title: 'T2' } })
    await mod.submit(4)
    expect(lastCall()).toMatchObject({ url: `/api/${name}/4/submit/`, method: 'POST' })
    await mod.returnToDraft(4, '缺少数据')
    expect(lastCall()).toEqual({ url: `/api/${name}/4/return/`, method: 'POST', body: { reason: '缺少数据' } })
    await mod.history(4)
    expect(lastCall()).toMatchObject({ url: `/api/${name}/4/history/`, method: 'GET' })
  })
})

describe('experiment write body', () => {
  it('uses the contract field names', async () => {
    const body = {
      project_id: 1, title: 'T', date: '2026-11-16', equipment_item_id: 4, equipment: '', specimen: '', specimen_item_ids: [5],
      params: { 频率: '5 MHz' }, steps: '', anomalies: '', dataset_ids: [3],
    }
    await experimentsApi.create(body)
    expect(lastCall().body).toEqual(body)
  })
})

import { afterEach, expect, it, vi } from 'vitest'
import { specimensApi } from './api'
afterEach(() => vi.unstubAllGlobals())
it('sends the seen loan id with the return request', async () => {
  const fetchMock = vi.fn().mockResolvedValue(new Response('{}', { status: 200 }))
  vi.stubGlobal('fetch', fetchMock)
  await specimensApi.giveBack(3, 11, '完好')
  const [url, init] = fetchMock.mock.calls[0]!
  expect(url).toBe('/api/specimens/3/return/')
  expect(init.method).toBe('POST')
  expect(JSON.parse(init.body)).toEqual({ loan_id_seen: 11, note: '完好' })
})

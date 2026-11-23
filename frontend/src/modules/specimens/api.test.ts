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

it('uses FormData when returning with an optional location photo', async () => {
  const fetchMock = vi.fn().mockResolvedValue(new Response('{}', { status: 200 }))
  vi.stubGlobal('fetch', fetchMock)
  const photo = new File([new Uint8Array([1, 2])], 'shelf.jpg', { type: 'image/jpeg' })
  await specimensApi.giveBack(3, 11, { note: '完好', return_location: 'A302 试块柜', photo })
  const [url, init] = fetchMock.mock.calls[0]!
  expect(url).toBe('/api/specimens/3/return/')
  expect(init.body).toBeInstanceOf(FormData)
  const form = init.body as FormData
  expect(form.get('loan_id_seen')).toBe('11')
  expect(form.get('return_location')).toBe('A302 试块柜')
  expect(form.get('photo')).toBe(photo)
})

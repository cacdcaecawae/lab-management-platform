// URL / method / body of every API module call, checked against docs/api-contract.md.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { bookingsApi } from './api'

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

describe('bookings', () => {
  it('lists a time window and cancels', async () => {
    await bookingsApi.list({ from: '2026-11-16T00:00:00.000Z', to: '2026-11-23T00:00:00.000Z', equipment: 2, mine: '' })
    expect(lastCall().url).toBe('/api/bookings/?from=2026-11-16T00%3A00%3A00.000Z&to=2026-11-23T00%3A00%3A00.000Z&equipment=2')
    await bookingsApi.cancel(5)
    expect(lastCall()).toMatchObject({ url: '/api/bookings/5/cancel/', method: 'POST' })
  })
  it('sends the usage report as multipart, photo only when given', async () => {
    await bookingsApi.report(5, { condition: 'abnormal', description: '无回波', photo: null })
    const [url, init] = fetchMock.mock.calls.at(-1)!
    expect(url).toBe('/api/bookings/5/report/')
    const form = init.body as FormData
    expect([form.get('condition'), form.get('description'), form.has('photo')]).toEqual(['abnormal', '无回波', false])
    const photo = new File(['x'], 'a.jpg', { type: 'image/jpeg' })
    await bookingsApi.report(5, { condition: 'normal', description: '', photo })
    expect((fetchMock.mock.calls.at(-1)![1].body as FormData).get('photo')).toBeInstanceOf(File)
  })
})

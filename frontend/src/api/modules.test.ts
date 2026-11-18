// URL / method / body of every API module call, checked against docs/api-contract.md.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { membersApi } from './members'
import { projectsApi } from './projects'
import { datasetsApi } from './datasets'
import { experimentsApi, runsApi } from './research'
import { reportsApi } from './reports'
import { dashboardApi } from './dashboard'
import { bookingsApi, consumablesApi } from './equipment'

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
      project_id: 1, title: 'T', date: '2026-11-16', equipment_item_id: 4, equipment: '', specimen: '',
      params: { 频率: '5 MHz' }, steps: '', anomalies: '', dataset_ids: [3],
    }
    await experimentsApi.create(body)
    expect(lastCall().body).toEqual(body)
  })
})

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
  })
})

describe('dashboard', () => {
  it('gets the dashboard', async () => {
    await dashboardApi.get()
    expect(lastCall()).toMatchObject({ url: '/api/dashboard/', method: 'GET' })
  })
})

describe('bookings and consumables', () => {
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
  it('posts stock transactions', async () => {
    const body = { kind: 'out' as const, quantity: 2, project_id: null, note: '' }
    await consumablesApi.addTxn(7, body)
    expect(lastCall()).toEqual({ url: '/api/consumables/7/txns/', method: 'POST', body })
  })
})

import { describe, expect, it } from 'vitest'
import {
  formatMoney,
  formatPeriod,
  formatSize,
  itemsTotal,
  mergeById,
  mondayOf,
  purchaseFileDeletable,
  toDateStr,
} from './format'
import { normalizeErrors } from './errors'
import { paramsProblem, toObject, toRows } from './params'

describe('dates', () => {
  it('uses the local calendar date', () => {
    expect(toDateStr(new Date(2026, 0, 5, 0, 30))).toBe('2026-01-05')
  })
  it('finds the monday of the week', () => {
    expect(mondayOf(new Date(2026, 10, 16))).toBe('2026-11-16') // Monday
    expect(mondayOf(new Date(2026, 10, 22))).toBe('2026-11-16') // Sunday
    expect(mondayOf(new Date(2026, 10, 4))).toBe('2026-11-02') // Wednesday, crosses no month
    expect(mondayOf(new Date(2026, 11, 2))).toBe('2026-11-30') // crosses month
  })
})

describe('formatSize', () => {
  it('formats bytes', () => {
    expect(formatSize(0)).toBe('0 B')
    expect(formatSize(1536)).toBe('1.5 KB')
    expect(formatSize(2 * 1024 ** 3)).toBe('2.0 GB')
  })
})

describe('mergeById', () => {
  it('appends embedded objects missing from the options', () => {
    expect(mergeById([{ id: 1 }], [{ id: 1 }, { id: 2 }, null])).toEqual([{ id: 1 }, { id: 2 }])
  })
})

describe('normalizeErrors', () => {
  it('maps backend keys onto form field names', () => {
    const known = ['project_id', 'input_ids', 'script_dataset_id', 'environment']
    expect(
      normalizeErrors({ project: ['必填'], inputs: ['至少 1 个'], script_dataset: ['二选一'], environment: ['必填'], x: ['?'] }, known),
    ).toEqual({ project_id: ['必填'], input_ids: ['至少 1 个'], script_dataset_id: ['二选一'], environment: ['必填'], x: ['?'] })
  })
  it('flattens nested serializer errors instead of throwing', () => {
    // DRF's answer for a bad second purchase item
    expect(normalizeErrors({ items: { 1: { link: ['请输入合法的URL。'], unit_price: ['必填'] } } }, ['items'])).toEqual({
      items: ['请输入合法的URL。', '必填'],
    })
  })
})

describe('params', () => {
  it('round-trips and keeps unedited non-string values', () => {
    const rows = toRows({ 增益: 30, 探头: '5L' })
    expect(toObject(rows)).toEqual({ 增益: 30, 探头: '5L' })
    rows[0].value = '31'
    expect(toObject(rows)).toEqual({ 增益: '31', 探头: '5L' })
  })
  it('drops empty rows and reports problems', () => {
    expect(toObject([{ key: ' ', value: '' }])).toEqual({})
    expect(paramsProblem([{ key: '', value: 'x' }])).toBe('有参数值没有填写参数名')
    expect(paramsProblem([{ key: 'a', value: '1' }, { key: 'a ', value: '2' }])).toBe('参数名重复：a')
    expect(paramsProblem([{ key: 'a', value: '1' }])).toBe('')
  })
})

describe('formatPeriod', () => {
  // Local times, so the test does not depend on the machine's time zone.
  const iso = (d: number, h: number) => new Date(2026, 10, d, h, 0).toISOString()
  it('omits the end date on the same day', () => {
    expect(formatPeriod(iso(18, 9), iso(18, 11))).toBe('2026-11-18 09:00 – 11:00')
  })
  it('keeps the end date across midnight', () => {
    expect(formatPeriod(iso(18, 22), iso(19, 2))).toBe('2026-11-18 22:00 – 2026-11-19 02:00')
  })
})

describe('money', () => {
  it('sums a purchase form in cents', () => {
    expect(itemsTotal([{ quantity: 3, unit_price: 0.1 }])).toBe(0.3)
    expect(itemsTotal([{ quantity: 2, unit_price: 1200 }, { quantity: 3, unit_price: 45.5 }, { quantity: 1, unit_price: undefined }])).toBe(2536.5)
  })
  it('formats with two decimals and separators', () => {
    expect(formatMoney('2536.5')).toBe('2,536.50')
    expect(formatMoney(null)).toBe('0.00')
  })
})

describe('purchaseFileDeletable', () => {
  const reviewed = [{ created_at: '2026-11-17T10:00:00+08:00' }]
  const before = { created_at: '2026-11-17T09:00:00+08:00' }
  const after = { created_at: '2026-11-17T10:05:00+08:00' }
  it('allows a draft, refuses under review, and afterwards only files no reviewer has seen', () => {
    expect(purchaseFileDeletable({ status: 'draft', approvals: reviewed }, before)).toBe(true)
    expect(purchaseFileDeletable({ status: 'pending_final', approvals: reviewed }, after)).toBe(false)
    expect(purchaseFileDeletable({ status: 'arrived', approvals: reviewed }, before)).toBe(false)
    expect(purchaseFileDeletable({ status: 'arrived', approvals: reviewed }, after)).toBe(true)
  })
})

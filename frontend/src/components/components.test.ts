import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import StatusTag from './StatusTag.vue'
import PinnedDatasets from './PinnedDatasets.vue'

const global = { plugins: [ElementPlus] }

describe('StatusTag', () => {
  it.each([
    ['draft', '草稿'],
    ['submitted', '已提交'],
    ['needs_revision', '需补充'],
    ['reviewed', '已阅'],
  ])('shows %s as %s', (status, label) => {
    expect(mount(StatusTag, { props: { status }, global }).text()).toBe(label)
  })
})

describe('PinnedDatasets', () => {
  it('shows the short version code, the "added since" mark, and older records without a version', () => {
    const datasets = [
      { id: 1, code: 'DS-2026-0001', name: '原始', kind: 'raw' as const, version: 'a'.repeat(64), changed: true },
      { id: 2, code: 'DS-2026-0002', name: '旧', kind: 'raw' as const, version: null, changed: false },
      null,
    ]
    const stubs = { RouterLink: { template: '<a><slot /></a>' } }
    const text = mount(PinnedDatasets, { props: { datasets }, global: { ...global, stubs } }).text()
    expect(text).toContain('DS-2026-0001 原始')
    expect(text).toContain(`@ ${'a'.repeat(12)}`)
    expect(text).not.toContain('a'.repeat(13))
    expect(text).toContain('提交后有新增')
    expect(text).toContain('无版本（旧记录）')
  })
})

// DESIGN.md: pages use the shared skeleton. These read the page sources and fail on the hand-rolled versions.
const pages = import.meta.glob<string>('/src/modules/**/*.vue', { query: '?raw', import: 'default', eager: true })
const offenders = (re: RegExp) => Object.keys(pages).filter((path) => re.test(pages[path]))

describe('pages use the shared skeleton (DESIGN.md)', () => {
  it('a dialog with a form is a FormDialog; el-dialog only shows content', () => {
    const withForm = Object.keys(pages).filter((path) =>
      (pages[path].match(/<el-dialog\b[\s\S]*?<\/el-dialog>/g) ?? []).some((dialog) => /<el-form\b|<el-input\b/.test(dialog)),
    )
    expect(withForm).toEqual([])
  })

  it('forms are laid out with .form-grid, not el-row / el-col', () => {
    expect(offenders(/<el-(row|col)\b/)).toEqual([])
  })

  it('list toolbars are PageToolbar and page headers are PageHeader', () => {
    expect(offenders(/class="page-toolbar"/)).toEqual([])
    expect(offenders(/<el-page-header\b/)).toEqual([])
  })

  it('new things are 新建, not 新增', () => {
    expect(offenders(/[>'"`]新增/)).toEqual([])
  })
})

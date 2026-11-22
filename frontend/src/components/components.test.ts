import { describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { Printer } from '@element-plus/icons-vue'
import StatusTag from './StatusTag.vue'
import IconButton from './IconButton.vue'
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

describe('IconButton', () => {
  it('is named by its label and passes clicks, disabled and links to the button', async () => {
    const onClick = vi.fn()
    const button = mount(IconButton, { props: { icon: Printer, label: '打印标签' }, attrs: { onClick }, global }).find('button')
    expect(button.attributes('aria-label')).toBe('打印标签')
    expect(button.text()).toBe('') // no words on the button itself
    await button.trigger('click')
    expect(onClick).toHaveBeenCalledOnce()
    const off = mount(IconButton, { props: { icon: Printer, label: '打印标签' }, attrs: { disabled: true }, global })
    expect(off.find('button').attributes('disabled')).toBeDefined()
    const link = mount(IconButton, { props: { icon: Printer, label: '导出 Excel' }, attrs: { tag: 'a', href: '/x.xlsx' }, global })
    expect(link.find('a').attributes()).toMatchObject({ href: '/x.xlsx', 'aria-label': '导出 Excel' })
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

  it('filters live in PageToolbar and apply on change: no inline filter forms, no 查询 button', () => {
    expect(offenders(/<el-form\b[^>]*\sinline\b|>\s*查询\s*<\/el-button>/)).toEqual([])
  })

  it('tool actions are IconButtons, not worded pills', () => {
    // the page's main button keeps its words (打印标签 on the labels page)
    const tool = /<el-button(?![^>]*type="primary")[^>]*>\s*(修改历史|打印标签|复制链接|换一个链接|导出[^<]*|[^<>]*统计|重新检查|全部标为已读)\s*<\/el-button>/
    expect(offenders(tool)).toEqual([])
  })

  it('every table says what is missing when empty (暂无 X), not the default 暂无数据', () => {
    const bare = Object.keys(pages).filter((path) =>
      (pages[path].match(/<el-table(?=[\s>])[^>]*>/g) ?? []).some((tag) => !/empty-text=/.test(tag)),
    )
    expect(bare).toEqual([])
  })

  it('every 操作 column is fixed="right" so phone cards place its actions at the bottom right', () => {
    const unfixed = Object.keys(pages).filter((path) =>
      (pages[path].match(/<el-table-column\b[^>]*label="操作"[^>]*>/g) ?? []).some((tag) => !/fixed="right"/.test(tag)),
    )
    expect(unfixed).toEqual([])
  })
})

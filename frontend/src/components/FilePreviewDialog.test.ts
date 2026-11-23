import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { MAX_PDF_PREVIEW_BYTES, isDelimitedFile, parseDelimitedRows, previewKindOf } from '@/utils/preview'
import FilePreviewDialog from './FilePreviewDialog.vue'

let createObjectURLMock: ReturnType<typeof vi.fn>
let revokeObjectURLMock: ReturnType<typeof vi.fn>

beforeEach(() => {
  createObjectURLMock = vi.fn(() => 'blob:mock-pdf-url')
  revokeObjectURLMock = vi.fn()
  vi.stubGlobal('URL', Object.assign(URL, { createObjectURL: createObjectURLMock, revokeObjectURL: revokeObjectURLMock }))
})

afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe('preview utils', () => {
  it('classifies safe previewable extensions and excludes active web types like svg/html', () => {
    expect(previewKindOf('scan.png')).toBe('image')
    expect(previewKindOf('photo.WEBP')).toBe('image')
    expect(previewKindOf('paper.pdf')).toBe('pdf')
    expect(previewKindOf('wave.csv')).toBe('text')
    expect(previewKindOf('script.py')).toBe('text')
    expect(previewKindOf('evil.svg')).toBeNull()
    expect(previewKindOf('evil.html')).toBeNull()
    expect(previewKindOf('archive.zip')).toBeNull()
  })

  it('parses CSV and TSV including quoted commas, escaped quotes, and multiline quoted cells', () => {
    expect(isDelimitedFile('a.csv')).toBe(',')
    expect(isDelimitedFile('a.tsv')).toBe('\t')
    expect(isDelimitedFile('a.txt')).toBeNull()

    const csv = '编号,备注,结果\r\n1,"第一行\n第二行","a""b,c"\r\n2,"含\r\n回车换行",正常\r\n'
    expect(parseDelimitedRows(csv, ',')).toEqual([
      ['编号', '备注', '结果'],
      ['1', '第一行\n第二行', 'a"b,c'],
      ['2', '含\n回车换行', '正常'],
    ])
  })
})

describe('FilePreviewDialog', () => {
  it('decodes GB18030 text from a regular attachment', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(Uint8Array.of(0xd6, 0xd0, 0xce, 0xc4))))
    const wrapper = mount(FilePreviewDialog, {
      props: { modelValue: true, target: { name: 'notes.txt', url: '/api/docs/1/download/' } },
      global: { plugins: [ElementPlus], stubs: { teleport: true } },
    })
    await flushPromises()
    expect(wrapper.text()).toContain('中文')
    wrapper.unmount()
  })

  it('renders a multiline quoted CSV record as a single table row', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ content: '名称,备注\n试件A,"第一行\n第二行"', truncated: false }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    )
    vi.stubGlobal('fetch', fetchMock)

    const wrapper = mount(FilePreviewDialog, {
      props: {
        modelValue: true,
        target: { name: 'notes.csv', url: '/api/files/1/download/', previewUrl: '/api/files/1/preview/', size: 64 },
      },
      global: { plugins: [ElementPlus], stubs: { teleport: true } },
    })
    await flushPromises()

    const rows = wrapper.findAll('.el-table__body-wrapper tbody tr')
    expect(rows).toHaveLength(1)
    expect(rows[0]!.text()).toContain('试件A')
    expect(rows[0]!.text()).toContain('第一行')
    expect(rows[0]!.text()).toContain('第二行')
    wrapper.unmount()
  })

  it('skips fetching PDFs larger than maxPdfBytes and offers fallback links', async () => {
    const fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)

    const wrapper = mount(FilePreviewDialog, {
      props: {
        modelValue: true,
        target: { name: 'huge.pdf', url: '/api/files/2/download/', previewUrl: '/api/files/2/preview/', size: MAX_PDF_PREVIEW_BYTES + 1 },
      },
      global: { plugins: [ElementPlus], stubs: { teleport: true } },
    })
    await flushPromises()

    expect(fetchMock).not.toHaveBeenCalled()
    expect(createObjectURLMock).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('超过弹窗预览上限')
    expect(wrapper.find('iframe').exists()).toBe(false)
    wrapper.unmount()
  })

  it('aborts streamed PDF download mid-flight when chunks exceed maxPdfBytes', async () => {
    const cancelMock = vi.fn().mockResolvedValue(undefined)
    let readCount = 0
    const stream = new ReadableStream<Uint8Array>({
      pull(controller) {
        readCount++
        if (readCount <= 3) controller.enqueue(new Uint8Array(600))
        else controller.close()
      },
      cancel: cancelMock,
    })
    let receivedSignal: AbortSignal | undefined
    const fetchMock = vi.fn((_url: string, init?: RequestInit) => {
      receivedSignal = init?.signal ?? undefined
      return Promise.resolve(new Response(stream, { status: 200 }))
    })
    vi.stubGlobal('fetch', fetchMock)

    const wrapper = mount(FilePreviewDialog, {
      props: {
        modelValue: true,
        maxPdfBytes: 1000,
        target: { name: 'stream-big.pdf', url: '/api/docs/1/download/' },
      },
      global: { plugins: [ElementPlus], stubs: { teleport: true } },
    })
    await flushPromises()

    expect(cancelMock).toHaveBeenCalled()
    expect(receivedSignal?.aborted).toBe(true)
    expect(createObjectURLMock).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('超过弹窗预览上限')
    wrapper.unmount()
  })

  it('aborts in-flight PDF fetch and never creates a blob URL when dialog is closed', async () => {
    let receivedSignal: AbortSignal | undefined
    let resolveFetch!: (res: Response) => void
    const fetchMock = vi.fn((_url: string, init?: RequestInit) => {
      receivedSignal = init?.signal ?? undefined
      return new Promise<Response>((resolve) => {
        resolveFetch = resolve
      })
    })
    vi.stubGlobal('fetch', fetchMock)

    const wrapper = mount(FilePreviewDialog, {
      props: {
        modelValue: true,
        target: { name: 'slow.pdf', url: '/api/docs/9/download/', size: 1024 },
      },
      global: { plugins: [ElementPlus], stubs: { teleport: true } },
    })
    await flushPromises()
    expect(receivedSignal?.aborted).toBe(false)

    // User closes dialog before PDF finishes downloading
    await wrapper.setProps({ modelValue: false })
    await flushPromises()
    expect(receivedSignal?.aborted).toBe(true)

    // Even if underlying fetch resolves after close, no blob URL is leaked
    resolveFetch(new Response(new Uint8Array([37, 80, 68, 70]), { status: 200 }))
    await flushPromises()
    expect(createObjectURLMock).not.toHaveBeenCalled()
    wrapper.unmount()
  })
})

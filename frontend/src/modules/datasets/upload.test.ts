import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '@/api/client'
import { uploadFile } from './api'

// Minimal XMLHttpRequest stand-in: records the request, the test decides the response.
class FakeXHR {
  static last: FakeXHR
  method = ''
  url = ''
  headers: Record<string, string> = {}
  body: FormData | null = null
  status = 0
  responseText = ''
  upload: { onprogress: ((e: { lengthComputable: boolean; loaded: number; total: number }) => void) | null } = { onprogress: null }
  onload: (() => void) | null = null
  onerror: (() => void) | null = null
  onabort: (() => void) | null = null
  constructor() {
    FakeXHR.last = this
  }
  open(method: string, url: string) {
    this.method = method
    this.url = url
  }
  setRequestHeader(k: string, v: string) {
    this.headers[k] = v
  }
  send(body: FormData) {
    this.body = body
  }
  respond(status: number, text: string) {
    this.status = status
    this.responseText = text
    this.onload?.()
  }
}

beforeEach(() => vi.stubGlobal('XMLHttpRequest', FakeXHR))
afterEach(() => vi.unstubAllGlobals())

const file = () => new File(['abc'], '数据.csv')

describe('uploadFile', () => {
  it('posts multipart with the csrf header and reports progress', async () => {
    document.cookie = 'csrftoken=tok42'
    const progress: number[] = []
    const p = uploadFile(9, file(), (n) => progress.push(n))
    const xhr = FakeXHR.last
    expect(xhr.method).toBe('POST')
    expect(xhr.url).toBe('/api/datasets/9/files/')
    expect(xhr.headers['X-CSRFToken']).toBe('tok42')
    expect(xhr.headers['Content-Type']).toBeUndefined() // browser sets the multipart boundary
    expect((xhr.body!.get('file') as File).name).toBe('数据.csv')
    xhr.upload.onprogress!({ lengthComputable: true, loaded: 1, total: 2 })
    xhr.respond(201, JSON.stringify([{ id: 1, name: '数据.csv' }]))
    await expect(p).resolves.toEqual([{ id: 1, name: '数据.csv' }])
    expect(progress).toEqual([50])
  })

  it('turns 409 file_exists into ApiError', async () => {
    const p = uploadFile(9, file())
    FakeXHR.last.respond(409, JSON.stringify({ code: 'file_exists', message: '文件已存在：数据.csv' }))
    const err = (await p.catch((e) => e)) as ApiError
    expect(err).toBeInstanceOf(ApiError)
    expect(err.status).toBe(409)
    expect(err.body.code).toBe('file_exists')
    expect(err.message).toBe('文件已存在：数据.csv')
  })

  it('turns 413 into file_too_large even with a non-JSON body', async () => {
    const p = uploadFile(9, file())
    FakeXHR.last.respond(413, '<html>413 Request Entity Too Large</html>')
    const err = (await p.catch((e) => e)) as ApiError
    expect(err.status).toBe(413)
    expect(err.body.code).toBe('file_too_large')
  })

  it('keeps validation errors from the body', async () => {
    const p = uploadFile(9, file())
    FakeXHR.last.respond(400, JSON.stringify({ code: 'validation_error', message: '提交的数据有误', errors: { file: ['文件名不能为空'] } }))
    const err = (await p.catch((e) => e)) as ApiError
    expect(err.body.errors).toEqual({ file: ['文件名不能为空'] })
  })

  it('turns a network failure into ApiError', async () => {
    const p = uploadFile(9, file())
    FakeXHR.last.onerror!()
    const err = (await p.catch((e) => e)) as ApiError
    expect(err).toBeInstanceOf(ApiError)
    expect(err.body.code).toBe('network_error')
  })
})

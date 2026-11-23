import { api, ApiError, csrfToken, type ApiErrorBody, type Page } from '@/api/client'
import type { DataFile, Dataset, DatasetReferences, DatasetWrite, ListQuery } from '@/api/types'

export const datasetsApi = {
  list: (q?: ListQuery) => api.get<Page<Dataset>>('/api/datasets/', q),
  get: (id: number) => api.get<Dataset>(`/api/datasets/${id}/`),
  create: (body: DatasetWrite) => api.post<Dataset>('/api/datasets/', body),
  update: (id: number, body: Partial<Pick<DatasetWrite, 'name' | 'description'>>) => api.patch<Dataset>(`/api/datasets/${id}/`, body),
  remove: (id: number) => api.delete(`/api/datasets/${id}/`),
  files: (id: number, version?: string) => api.get<DataFile[]>(`/api/datasets/${id}/files/`, { version }),
  references: (id: number) => api.get<DatasetReferences>(`/api/datasets/${id}/references/`),
  downloadZipUrl: (id: number, version?: string) =>
    version ? `/api/datasets/${id}/download-zip/?version=${encodeURIComponent(version)}` : `/api/datasets/${id}/download-zip/`,
  uploadFile,
}

// Non-JSON error bodies (e.g. a proxy's HTML 413 page) still become a uniform ApiError.
function fallbackBody(status: number): ApiErrorBody {
  if (status === 413) return { code: 'file_too_large', message: '文件超过大小上限' }
  return { code: `http_${status}`, message: `请求失败（${status}）` }
}

// One file per request so each file has its own progress and a 409 on one file does not block the others.
export function uploadFile(datasetId: number, file: File, onProgress?: (percent: number) => void): Promise<DataFile[]> {
  const form = new FormData()
  form.append('file', file)
  return uploadForm<DataFile[]>(`/api/datasets/${datasetId}/files/`, form, onProgress)
}

// XMLHttpRequest instead of fetch: fetch cannot report upload progress.
export function uploadForm<T>(path: string, form: FormData, onProgress?: (percent: number) => void): Promise<T> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest()
    xhr.open('POST', path)
    xhr.setRequestHeader('Accept', 'application/json')
    xhr.setRequestHeader('X-CSRFToken', csrfToken())
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable) onProgress?.(Math.round((e.loaded / e.total) * 100))
    }
    xhr.onload = () => {
      let data: unknown = null
      try {
        data = JSON.parse(xhr.responseText)
      } catch {
        // non-JSON body: handled below
      }
      if (xhr.status >= 200 && xhr.status < 300) resolve(data as T)
      else {
        const body = data as ApiErrorBody | null
        reject(new ApiError(xhr.status, body && typeof body.code === 'string' ? body : fallbackBody(xhr.status)))
      }
    }
    xhr.onerror = () => reject(new ApiError(0, { code: 'network_error', message: '网络错误，上传失败' }))
    xhr.onabort = () => reject(new ApiError(0, { code: 'aborted', message: '上传已取消' }))
    xhr.send(form)
  })
}

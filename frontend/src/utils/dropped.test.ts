import { describe, expect, it } from 'vitest'
import { droppedFiles } from './dropped'

// Minimal stand-ins for the browser's FileSystemEntry tree.
function fileEntry(name: string) {
  return { isFile: true, isDirectory: false, name, file: (ok: (f: File) => void) => ok(new File([name], name)) }
}
function folder(name: string, children: unknown[], batch = 2) {
  return {
    isFile: false,
    isDirectory: true,
    name,
    createReader: () => {
      let at = 0
      // like Chrome, a folder is read in batches until an empty one
      return { readEntries: (ok: (e: unknown[]) => void) => ok(children.slice(at, (at += batch))) }
    },
  }
}
function drop(entries: unknown[], files: File[] = []) {
  return { items: entries.map((e) => ({ webkitGetAsEntry: () => e })), files } as unknown as DataTransfer
}

describe('droppedFiles', () => {
  it('opens folders and keeps each file\'s path in them', async () => {
    const data = drop([
      folder('采集', [fileEntry('a.csv'), folder('ch1', [fileEntry('data.csv')]), fileEntry('Thumbs.db'), fileEntry('b.csv')]),
      fileEntry('说明.txt'),
    ])
    const found = await droppedFiles(data)
    expect(found.map((f) => [f.path, f.file.name])).toEqual([
      ['采集/a.csv', 'a.csv'],
      ['采集/ch1/data.csv', 'data.csv'],
      ['采集/b.csv', 'b.csv'],
      ['', '说明.txt'], // dropped on its own: no path
    ])
  })

  it('takes plain files as they are', async () => {
    const files = [new File(['1'], 'w1.csv'), new File(['2'], 'w2.csv')]
    const found = await droppedFiles(drop([fileEntry('w1.csv'), fileEntry('w2.csv')], files))
    expect(found).toEqual([{ file: files[0], path: '' }, { file: files[1], path: '' }])
  })
})

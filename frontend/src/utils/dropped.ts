// Files dropped onto a page, with dropped folders opened: a file from a folder keeps its path in it
// ("采集/ch1/data.csv"), so the same file name in two subfolders does not collide. A file dropped on its own has path ''.
export interface DroppedFile {
  file: File
  path: string
}

const SYSTEM_FILES = new Set(['.DS_Store', 'Thumbs.db', 'desktop.ini']) // left by the OS in folders, never data

export function droppedFiles(data: DataTransfer): Promise<DroppedFile[]> {
  // The entries must be taken while the drop event runs (synchronously, before any await); they are read afterwards.
  const entries = Array.from(data.items ?? []).map((item) => item.webkitGetAsEntry?.() ?? null)
  if (!entries.some((entry) => entry?.isDirectory)) {
    return Promise.resolve(Array.from(data.files).map((file) => ({ file, path: '' })))
  }
  return (async () => {
    const found: DroppedFile[] = []
    for (const entry of entries) if (entry) await walk(entry, '', found)
    return found
  })()
}

async function walk(entry: FileSystemEntry, folder: string, found: DroppedFile[]) {
  if (entry.isFile) {
    if (SYSTEM_FILES.has(entry.name)) return
    const file = await new Promise<File>((resolve, reject) => (entry as FileSystemFileEntry).file(resolve, reject))
    found.push({ file, path: folder ? `${folder}/${file.name}` : '' })
    return
  }
  const path = folder ? `${folder}/${entry.name}` : entry.name
  const reader = (entry as FileSystemDirectoryEntry).createReader()
  // readEntries hands out a folder's entries in batches (100 at a time in Chrome) until a batch is empty
  for (;;) {
    const batch = await new Promise<FileSystemEntry[]>((resolve, reject) => reader.readEntries(resolve, reject))
    if (!batch.length) return
    for (const child of batch) await walk(child, path, found)
  }
}

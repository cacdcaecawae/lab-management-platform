export type PreviewKind = 'image' | 'pdf' | 'text'

const IMAGE_EXT = /\.(png|jpe?g|gif|webp)$/i
const PDF_EXT = /\.pdf$/i
const TEXT_EXT = /\.(csv|tsv|txt|md|json|ya?ml|log|py|m|c|h|cpp|ini|toml)$/i

export function previewKindOf(name: string): PreviewKind | null {
  if (IMAGE_EXT.test(name)) return 'image'
  if (PDF_EXT.test(name)) return 'pdf'
  if (TEXT_EXT.test(name)) return 'text'
  return null
}

export function isDelimitedFile(name: string): ',' | '\t' | null {
  if (/\.csv$/i.test(name)) return ','
  if (/\.tsv$/i.test(name)) return '\t'
  return null
}

// Lightweight RFC-4180-compatible single-line CSV/TSV splitter for preview tables (zero extra deps).
export function parseDelimitedRows(content: string, delimiter: ',' | '\t'): string[][] {
  const rows: string[][] = []
  for (const line of content.split(/\r?\n/)) {
    if (!line.length && rows.length > 0) continue
    const cells: string[] = []
    let cur = ''
    let inQuotes = false
    for (let i = 0; i < line.length; i++) {
      const ch = line[i]
      if (inQuotes) {
        if (ch === '"' && line[i + 1] === '"') {
          cur += '"'
          i++
        } else if (ch === '"') {
          inQuotes = false
        } else {
          cur += ch
        }
      } else if (ch === '"') {
        inQuotes = true
      } else if (ch === delimiter) {
        cells.push(cur)
        cur = ''
      } else {
        cur += ch
      }
    }
    cells.push(cur)
    rows.push(cells)
  }
  return rows
}

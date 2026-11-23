export type PreviewKind = 'image' | 'pdf' | 'text'

// Cap in-dialog PDF blob buffering so large PDFs never exhaust browser memory.
export const MAX_PDF_PREVIEW_BYTES = 20 * 1024 * 1024 // 20 MB

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

// Single-pass RFC-4180 CSV/TSV parser supporting quoted newlines, escaped quotes (""), and CRLF/LF.
export function parseDelimitedRows(content: string, delimiter: ',' | '\t'): string[][] {
  if (!content) return []
  const rows: string[][] = []
  let cells: string[] = []
  let cur = ''
  let inQuotes = false
  let atCellStart = true

  for (let i = 0; i < content.length; i++) {
    const ch = content[i]
    if (inQuotes) {
      if (ch === '"') {
        if (content[i + 1] === '"') {
          cur += '"'
          i++
        } else {
          inQuotes = false
        }
      } else if (ch === '\r') {
        if (content[i + 1] === '\n') i++
        cur += '\n'
      } else {
        cur += ch
      }
    } else if (ch === '"' && atCellStart) {
      inQuotes = true
      atCellStart = false
    } else if (ch === delimiter) {
      cells.push(cur)
      cur = ''
      atCellStart = true
    } else if (ch === '\r' || ch === '\n') {
      if (ch === '\r' && content[i + 1] === '\n') i++
      cells.push(cur)
      if (cells.length > 1 || cells[0] !== '' || rows.length === 0) {
        rows.push(cells)
      }
      cells = []
      cur = ''
      atCellStart = true
    } else {
      cur += ch
      atCellStart = false
    }
  }

  if (!atCellStart || cells.length > 0) {
    cells.push(cur)
    rows.push(cells)
  }
  return rows
}

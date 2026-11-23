import { describe, expect, it } from 'vitest'
import { isDelimitedFile, parseDelimitedRows, previewKindOf } from '@/utils/preview'

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

  it('parses CSV and TSV with quoted commas', () => {
    expect(isDelimitedFile('a.csv')).toBe(',')
    expect(isDelimitedFile('a.tsv')).toBe('\t')
    expect(isDelimitedFile('a.txt')).toBeNull()
    expect(parseDelimitedRows('col1,"col,2"\n1,"a""b"', ',')).toEqual([
      ['col1', 'col,2'],
      ['1', 'a"b'],
    ])
  })
})

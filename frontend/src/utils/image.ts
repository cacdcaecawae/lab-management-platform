// Client-side image helpers so the server needs no image library (no Pillow dependency).
// Rejects if the browser cannot decode the image (e.g. HEIC on desktop browsers).

export async function squareJpeg(file: Blob, size = 256): Promise<Blob> {
  const image = await createImageBitmap(file)
  const side = Math.min(image.width, image.height)
  const canvas = document.createElement('canvas')
  canvas.width = canvas.height = size
  const ctx = canvas.getContext('2d')!
  ctx.fillStyle = '#fff'
  ctx.fillRect(0, 0, size, size)
  ctx.drawImage(image, (image.width - side) / 2, (image.height - side) / 2, side, side, 0, 0, size, size)
  image.close()
  return new Promise((resolve, reject) =>
    canvas.toBlob((blob) => (blob ? resolve(blob) : reject(new Error('图片转换失败'))), 'image/jpeg', 0.9),
  )
}

export async function resizeJpeg(file: Blob, maxEdge = 1920, quality = 0.85): Promise<Blob> {
  const image = await createImageBitmap(file)
  const longest = Math.max(image.width, image.height)
  const scale = longest > maxEdge ? maxEdge / longest : 1
  const width = Math.max(1, Math.round(image.width * scale))
  const height = Math.max(1, Math.round(image.height * scale))
  const canvas = document.createElement('canvas')
  canvas.width = width
  canvas.height = height
  const ctx = canvas.getContext('2d')!
  ctx.fillStyle = '#fff'
  ctx.fillRect(0, 0, width, height)
  ctx.drawImage(image, 0, 0, width, height)
  image.close()
  return new Promise((resolve, reject) =>
    canvas.toBlob((blob) => (blob ? resolve(blob) : reject(new Error('图片转换失败'))), 'image/jpeg', quality),
  )
}

const ACCEPTED_EXT = /\.(jpe?g|png|webp)$/i

// Compresses large camera photos into a standard JPEG so phone shots stay fast and within the 10 MB limit.
export async function preparePhoto(file: File, maxEdge = 1920, quality = 0.85): Promise<File> {
  if (typeof createImageBitmap !== 'function') {
    if (ACCEPTED_EXT.test(file.name)) return file
    throw new Error('只支持 JPG、PNG、WebP 图片')
  }
  const stem = file.name.replace(/\.[^.]+$/, '') || 'photo'
  const needsConvert = !ACCEPTED_EXT.test(file.name) || file.size > 400 * 1024
  if (!needsConvert) return file
  const blob = await resizeJpeg(file, maxEdge, quality)
  return new File([blob], `${stem}.jpg`, { type: 'image/jpeg' })
}

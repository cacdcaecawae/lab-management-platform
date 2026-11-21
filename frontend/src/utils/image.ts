// The avatar the page uploads: the middle square of the picture, 256px, as JPEG (transparent areas white), so the
// server keeps a small file and needs no image library. Rejects if the browser cannot read the picture (e.g. HEIC).
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

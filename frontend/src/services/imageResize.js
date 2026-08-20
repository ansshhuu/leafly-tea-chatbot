const MAX_WIDTH = 800
const JPEG_QUALITY = 0.8

export async function resizeImageForUpload(file, { maxWidth = MAX_WIDTH, quality = JPEG_QUALITY } = {}) {
  try {
    const bitmap = await createImageBitmap(file)
    const scale = Math.min(1, maxWidth / bitmap.width)
    const width = Math.round(bitmap.width * scale)
    const height = Math.round(bitmap.height * scale)

    const canvas = document.createElement('canvas')
    canvas.width = width
    canvas.height = height
    const ctx = canvas.getContext('2d')
    ctx.drawImage(bitmap, 0, 0, width, height)
    bitmap.close?.()

    const blob = await new Promise((resolve) => canvas.toBlob(resolve, 'image/jpeg', quality))
    if (!blob) return file

    const resizedName = file.name.replace(/\.\w+$/, '') + '.jpg'
    return new File([blob], resizedName, { type: 'image/jpeg' })
  } catch {
    return file
  }
}

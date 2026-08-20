import { useRef, useState } from 'react'
import { ALLOWED_IMAGE_TYPES, MAX_IMAGE_BYTES } from '../../services/api'
import { resizeImageForUpload } from '../../services/imageResize'
import './ImageUpload.css'

export default function ImageUpload({ onSelect, disabled }) {
  const inputRef = useRef(null)
  const [error, setError] = useState(null)
  const [isPreparing, setIsPreparing] = useState(false)

  async function handleChange(event) {
    const file = event.target.files?.[0]
    event.target.value = ''
    if (!file) return

    if (!ALLOWED_IMAGE_TYPES.includes(file.type)) {
      setError('Only JPG and PNG images are supported.')
      return
    }
    if (file.size > MAX_IMAGE_BYTES) {
      setError('Image must be 5MB or smaller.')
      return
    }

    setError(null)
    setIsPreparing(true)
    try {
      const resized = await resizeImageForUpload(file)
      onSelect(resized)
    } finally {
      setIsPreparing(false)
    }
  }

  return (
    <div className="image-upload">
      <button
        type="button"
        className="image-upload-btn"
        onClick={() => inputRef.current?.click()}
        disabled={disabled || isPreparing}
        aria-label="Upload a photo"
        title="Upload a photo"
      >
        <svg viewBox="0 0 24 24" width="18" height="18" fill="none" aria-hidden="true">
          <path
            d="M17.5 8.5 9 17a3.5 3.5 0 1 1-5-5l8.5-8.5a2.5 2.5 0 1 1 3.5 3.5L7.5 15.5a1.5 1.5 0 1 1-2-2L13 6"
            stroke="currentColor"
            strokeWidth="1.7"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
      </button>
      <input
        ref={inputRef}
        type="file"
        accept="image/jpeg,image/png"
        onChange={handleChange}
        hidden
        aria-hidden="true"
        tabIndex={-1}
      />
      {error && (
        <span className="image-upload-error" role="status">
          {error}
        </span>
      )}
    </div>
  )
}

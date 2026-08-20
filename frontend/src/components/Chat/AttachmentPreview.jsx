import './AttachmentPreview.css'

export default function AttachmentPreview({ previewUrl, onRemove }) {
  if (!previewUrl) return null

  return (
    <div className="attachment-preview">
      <div className="attachment-preview-thumb-wrap">
        <img src={previewUrl} alt="Attached photo preview" className="attachment-preview-thumb" />
        <button
          type="button"
          className="attachment-preview-remove"
          onClick={onRemove}
          aria-label="Remove attached photo"
          title="Remove photo"
        >
          ✕
        </button>
      </div>
    </div>
  )
}

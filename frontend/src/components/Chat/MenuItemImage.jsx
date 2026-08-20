import { useState } from 'react'
import { ImageIcon } from 'lucide-react'

export default function MenuItemImage({ imageUrl, name }) {
  const [failed, setFailed] = useState(false)

  if (imageUrl && !failed) {
    return (
      <div className="menu-item-image">
        <img src={imageUrl} alt={name} onError={() => setFailed(true)} />
      </div>
    )
  }
  return (
    <div className="menu-item-image menu-item-image--placeholder" aria-hidden="true">
      <ImageIcon size={18} strokeWidth={1.5} />
    </div>
  )
}

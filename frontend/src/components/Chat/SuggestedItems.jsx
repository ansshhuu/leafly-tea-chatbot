import MenuItemImage from './MenuItemImage'
import './SuggestedItems.css'

function formatPrice(price) {
  return Number(price).toString()
}

export default function SuggestedItems({ items }) {
  if (!items || items.length === 0) return null

  return (
    <ul className="suggested-items">
      {items.map((item) => (
        <li key={item.name} className="suggested-item-card">
          <MenuItemImage imageUrl={item.image_url} name={item.name} />
          <span className="suggested-item-name">{item.name}</span>
          <span className="suggested-item-price">Rs.{formatPrice(item.price)}</span>
        </li>
      ))}
    </ul>
  )
}

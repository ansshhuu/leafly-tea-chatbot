import { useState } from 'react'
import { ArrowLeft, Gift, Leaf } from 'lucide-react'
import MenuItemImage from './MenuItemImage'
import './MenuDisplay.css'

function formatPrice(price) {
  return Number(price).toString()
}

const CATEGORY_ICONS = {
  'Gift Hampers': Gift,
}

function MenuItemRow({ item }) {
  return (
    <li className="menu-item-row">
      <MenuItemImage imageUrl={item.image_url} name={item.name} />
      <div className="menu-item-body">
        <span className="menu-item-name">{item.name}</span>
      </div>
      <span className="menu-item-price">Rs.{formatPrice(item.price)}</span>
    </li>
  )
}

const PREVIEW_LIMIT = 3

export default function MenuDisplay({ categories }) {
  const nonEmptyCategories = (categories || []).filter((c) => c.items.length > 0)
  const [activeCategory, setActiveCategory] = useState(() => nonEmptyCategories[0]?.category ?? null)
  const [expanded, setExpanded] = useState(false)
  const [closed, setClosed] = useState(false)

  if (nonEmptyCategories.length === 0) return null

  if (closed) {
    return (
      <button type="button" className="menu-reopen-btn" onClick={() => setClosed(false)}>
        <Leaf size={16} strokeWidth={1.75} aria-hidden="true" />
        Show teas
      </button>
    )
  }

  function handleTabClick(category) {
    setActiveCategory(category)
    setExpanded(false)
  }

  const activeCategoryItems = nonEmptyCategories.find((c) => c.category === activeCategory)?.items ?? []
  const hasMore = activeCategoryItems.length > PREVIEW_LIMIT
  const visibleItems = expanded ? activeCategoryItems : activeCategoryItems.slice(0, PREVIEW_LIMIT)

  return (
    <div className="menu-display">
      <div className="menu-display-header">
        <button type="button" className="menu-back-btn" onClick={() => setClosed(true)} aria-label="Close menu">
          <ArrowLeft size={18} strokeWidth={1.75} />
        </button>
        <h3 className="menu-display-title">Our Teas</h3>
        <Leaf className="menu-display-deco-icon" size={18} strokeWidth={1.75} aria-hidden="true" />
      </div>

      <div className="menu-tabs" role="tablist" aria-label="Menu categories">
        {nonEmptyCategories.map(({ category }) => {
          const Icon = CATEGORY_ICONS[category] || Leaf
          const isActive = category === activeCategory
          return (
            <button
              key={category}
              type="button"
              role="tab"
              aria-selected={isActive}
              className={`menu-tab ${isActive ? 'menu-tab--active' : ''}`}
              onClick={() => handleTabClick(category)}
            >
              <Icon size={12} strokeWidth={1.75} aria-hidden="true" />
              {category}
            </button>
          )
        })}
      </div>

      <ul className={`menu-item-list ${expanded ? 'menu-item-list--expanded' : ''}`}>
        {visibleItems.map((item) => (
          <MenuItemRow key={`${item.category}-${item.name}`} item={item} />
        ))}
      </ul>

      {hasMore && (
        <button type="button" className="menu-see-all-btn" onClick={() => setExpanded((prev) => !prev)}>
          {expanded ? 'Show less' : 'See all items'}
        </button>
      )}
    </div>
  )
}

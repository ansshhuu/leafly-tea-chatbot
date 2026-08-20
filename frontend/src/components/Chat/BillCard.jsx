import './BillCard.css'

function formatMoney(amount) {
  return Number(amount).toFixed(2)
}

export default function BillCard({ summary }) {
  if (!summary) return null

  const isConfirmed = summary.status === 'confirmed'
  // Nothing worth showing for a draft with zero items - only a confirmed
  // order (which always has items) or a non-empty draft gets a bill card.
  if (!isConfirmed && (!summary.items || summary.items.length === 0)) return null

  const hasDiscount = Boolean(summary.discount)

  return (
    <div className={`bill-card ${isConfirmed ? 'bill-card--confirmed' : ''}`}>
      <div className="bill-card-header">
        <span>{isConfirmed ? 'Order Confirmed' : 'Your Order'}</span>
        <span className="bill-card-status">{summary.status}</span>
      </div>

      <ul className="bill-card-items">
        {summary.items.map((item) => (
          <li key={item.menu_item_id} className="bill-card-row">
            <span className="bill-card-item-name">{item.name}</span>
            <span className="bill-card-item-qty">x{item.quantity}</span>
            <span className="bill-card-item-price">Rs.{formatMoney(item.price_at_order)}</span>
            <span className="bill-card-item-total">Rs.{formatMoney(item.line_total)}</span>
          </li>
        ))}
      </ul>

      <div className="bill-card-totals">
        <div className="bill-card-total-row">
          <span>{hasDiscount ? 'Original Price' : 'Subtotal'}</span>
          <span>Rs.{formatMoney(summary.subtotal)}</span>
        </div>
        {hasDiscount && (
          <div className="bill-card-total-row bill-card-total-row--discount">
            <span>Coupon Applied ({summary.coupon_code})</span>
            <span>-Rs.{formatMoney(summary.discount)}</span>
          </div>
        )}
        <div className="bill-card-total-row">
          <span>Tax</span>
          <span>Rs.{formatMoney(summary.tax)}</span>
        </div>
        <div className="bill-card-total-row bill-card-total-row--grand">
          <span>{hasDiscount ? 'Final Amount' : 'Total'}</span>
          <span>Rs.{formatMoney(summary.total)}</span>
        </div>
        {hasDiscount && (
          <p className="bill-card-savings">You saved Rs.{formatMoney(summary.discount)}! 🎉</p>
        )}
      </div>
    </div>
  )
}

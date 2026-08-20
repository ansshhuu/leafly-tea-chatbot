import AddressMap from './AddressMap'
import BillCard from './BillCard'
import DatePicker from './DatePicker'
import LocationCards from './LocationCards'
import LoyaltyCard from './LoyaltyCard'
import MenuDisplay from './MenuDisplay'
import MockPaymentCard from './MockPaymentCard'
import QuickActions, { isQuickActionLabelSet } from './QuickActions'
import QuickReplyOptions from './QuickReplyOptions'
import ReadReceipt from './ReadReceipt'
import SuggestedItems from './SuggestedItems'
import Timestamp from './Timestamp'
import './MessageBubble.css'

export default function MessageBubble({
  role,
  text,
  timestamp,
  imageUrl,
  menuDisplay,
  suggestedItems,
  orderSummary,
  quickReplyOptions,
  datePickerOptions,
  paymentRequest,
  loyaltyCard,
  locationCards,
  awaitingAddressInput,
  status,
  isLatest = true,
}) {
  const isUser = role === 'user'
  const isSystem = role === 'system'
  const isAssistant = !isUser && !isSystem
  const bubbleModifier = isUser ? 'user' : isSystem ? 'system' : 'assistant'
  const hasMenu = Boolean(menuDisplay && menuDisplay.length > 0)
  const hasSuggestions = Boolean(suggestedItems && suggestedItems.length > 0)
  const hasBill = Boolean(orderSummary)
  const hasQuickReplies = Boolean(quickReplyOptions && quickReplyOptions.length > 0)
  const hasDatePicker = Boolean(datePickerOptions && datePickerOptions.length > 0)
  const hasPaymentRequest = Boolean(paymentRequest)
  const hasLoyaltyCard = Boolean(loyaltyCard)
  const hasLocationCards = Boolean(locationCards && locationCards.length > 0)
  const hasAddressMap = Boolean(awaitingAddressInput)
  const isQuickActions = hasQuickReplies && isQuickActionLabelSet(quickReplyOptions)
  const isRich =
    hasMenu ||
    hasSuggestions ||
    hasBill ||
    hasDatePicker ||
    hasPaymentRequest ||
    hasLoyaltyCard ||
    hasLocationCards ||
    hasAddressMap

  return (
    <div className={`message-row ${isUser ? 'message-row--user' : 'message-row--assistant'}`}>
      {isAssistant && (
        <span className="message-avatar" aria-hidden="true">
          <img src="/bot-icon.png" alt="" />
        </span>
      )}
      <div className={`message-bubble message-bubble--${bubbleModifier} ${isRich ? 'message-bubble--rich' : ''}`}>
        {imageUrl && (
          <img
            className="message-image"
            src={imageUrl}
            alt={text ? `Photo shared with message: ${text}` : 'Photo shared by the customer'}
          />
        )}
        {text && <p className="message-text">{text}</p>}
        {hasMenu && <MenuDisplay categories={menuDisplay} />}
        {hasSuggestions && <SuggestedItems items={suggestedItems} />}
        {hasBill && <BillCard summary={orderSummary} />}
        {hasLoyaltyCard && <LoyaltyCard card={loyaltyCard} />}
        {hasLocationCards && <LocationCards locations={locationCards} />}
        {hasDatePicker && <DatePicker options={datePickerOptions} disabled={!isLatest} />}
        {hasAddressMap && <AddressMap disabled={!isLatest} />}
        {hasPaymentRequest && (
          <MockPaymentCard amount={paymentRequest.amount} label={paymentRequest.label} disabled={!isLatest} />
        )}
        {isQuickActions && <QuickActions disabled={!isLatest} />}
        {hasQuickReplies && !isQuickActions && (
          <QuickReplyOptions options={quickReplyOptions} disabled={!isLatest} />
        )}
        <div className="message-footer">
          <Timestamp isoString={timestamp} />
          {isUser && <ReadReceipt status={status} />}
        </div>
      </div>
    </div>
  )
}

import LocationCards from './LocationCards'
import MenuDisplay from './MenuDisplay'
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
  menuDisplay,
  suggestedItems,
  quickReplyOptions,
  locationCards,
  status,
  isLatest = true,
}) {
  const isUser = role === 'user'
  const isSystem = role === 'system'
  const isAssistant = !isUser && !isSystem
  const bubbleModifier = isUser ? 'user' : isSystem ? 'system' : 'assistant'
  const hasMenu = Boolean(menuDisplay && menuDisplay.length > 0)
  const hasSuggestions = Boolean(suggestedItems && suggestedItems.length > 0)
  const hasQuickReplies = Boolean(quickReplyOptions && quickReplyOptions.length > 0)
  const hasLocationCards = Boolean(locationCards && locationCards.length > 0)
  const isQuickActions = hasQuickReplies && isQuickActionLabelSet(quickReplyOptions)
  const isRich = hasMenu || hasSuggestions || hasLocationCards

  return (
    <div className={`message-row ${isUser ? 'message-row--user' : 'message-row--assistant'}`}>
      {isAssistant && (
        <span className="message-avatar" aria-hidden="true">
          <img src="/bot-icon.png" alt="" />
        </span>
      )}
      <div className={`message-bubble message-bubble--${bubbleModifier} ${isRich ? 'message-bubble--rich' : ''}`}>
        {text && <p className="message-text">{text}</p>}
        {hasMenu && <MenuDisplay categories={menuDisplay} />}
        {hasSuggestions && <SuggestedItems items={suggestedItems} />}
        {hasLocationCards && <LocationCards locations={locationCards} />}
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

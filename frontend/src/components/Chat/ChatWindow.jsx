import { useEffect, useMemo, useRef, useState } from 'react'
import { Leaf } from 'lucide-react'
import MessageBubble from './MessageBubble'
import TypingIndicator from './TypingIndicator'
import WelcomeScreen from './WelcomeScreen'
import { isQuickActionLabelSet } from './QuickActions'
import { useChat } from '../../context/ChatContext'
import './ChatWindow.css'

const TEXTAREA_MAX_HEIGHT = 120
const SINGLE_LINE_THRESHOLD = 44
const BUTTON_ONLY_PLACEHOLDER = 'Please select an option above'
const DEFAULT_PLACEHOLDER = 'Ask me anything...'

// True when the latest assistant message expects a quick-reply tap rather
// than free text. The general_chat "quick action" suggestions (View
// Products, Gift Hampers, ...) are NOT gating - those are just shortcuts,
// so free text stays enabled for them.
function isButtonOnlyStep(message) {
  if (!message || message.role !== 'assistant') return false
  if (message.quickReplyOptions && message.quickReplyOptions.length > 0) {
    return !isQuickActionLabelSet(message.quickReplyOptions)
  }
  return false
}

export default function ChatWindow() {
  const { messages, isTyping, sendUserMessage } = useChat()
  const [draft, setDraft] = useState('')
  const [isMultiline, setIsMultiline] = useState(false)
  const listRef = useRef(null)
  const inputRef = useRef(null)

  useEffect(() => {
    if (listRef.current) {
      listRef.current.scrollTop = listRef.current.scrollHeight
    }
  }, [messages, isTyping])

  useEffect(() => {
    const el = inputRef.current
    if (!el) return
    el.style.height = 'auto'
    const next = Math.min(el.scrollHeight, TEXTAREA_MAX_HEIGHT)
    el.style.height = `${next}px`
    setIsMultiline(el.scrollHeight > SINGLE_LINE_THRESHOLD)
  }, [draft])

  function handleDraftChange(e) {
    setDraft(e.target.value)
  }

  function resetDraft() {
    setDraft('')
  }

  function submitMessage() {
    const text = draft.trim()
    if (isTyping || inputBlocked) return
    if (!text) return

    sendUserMessage(text)
    resetDraft()
  }

  function handleFormSubmit(e) {
    e.preventDefault()
    submitMessage()
  }

  function handleKeyDown(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      submitMessage()
    }
  }

  const inputBlocked = useMemo(() => isButtonOnlyStep(messages[messages.length - 1]), [messages])
  const canSend = !isTyping && !inputBlocked && draft.trim().length > 0
  const isWelcomeState = messages.length === 1 && messages[0].id === 'welcome-1'

  return (
    <div className="chat-window">
      <div className="chat-messages" ref={listRef}>
        {isWelcomeState ? (
          <WelcomeScreen text={messages[0].text} />
        ) : (
          <>
            {messages.length === 0 && (
              <p className="chat-empty-state">No messages yet - say hello or ask about the menu!</p>
            )}
            {messages.map((msg, index) => (
              <MessageBubble
                key={msg.id}
                role={msg.role}
                text={msg.text}
                timestamp={msg.timestamp}
                menuDisplay={msg.menuDisplay}
                suggestedItems={msg.suggestedItems}
                quickReplyOptions={msg.quickReplyOptions}
                locationCards={msg.locationCards}
                status={msg.status}
                isLatest={index === messages.length - 1}
              />
            ))}
            <TypingIndicator show={isTyping} />
          </>
        )}
      </div>

      <form className="chat-input-bar" onSubmit={handleFormSubmit}>
        <textarea
          ref={inputRef}
          className={`chat-input ${isMultiline ? 'chat-input--multiline' : ''}`}
          placeholder={inputBlocked ? BUTTON_ONLY_PLACEHOLDER : DEFAULT_PLACEHOLDER}
          value={draft}
          onChange={handleDraftChange}
          onKeyDown={handleKeyDown}
          disabled={isTyping || inputBlocked}
          rows={1}
          aria-label={inputBlocked ? BUTTON_ONLY_PLACEHOLDER : 'Message'}
        />
        <button className="chat-send-btn" type="submit" disabled={!canSend} aria-label="Send message">
          <Leaf size={16} strokeWidth={2} aria-hidden="true" />
        </button>
      </form>
    </div>
  )
}

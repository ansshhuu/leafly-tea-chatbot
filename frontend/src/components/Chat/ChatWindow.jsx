import { useEffect, useMemo, useRef, useState } from 'react'
import AttachmentPreview from './AttachmentPreview'
import MessageBubble from './MessageBubble'
import TypingIndicator from './TypingIndicator'
import VoiceInput from './VoiceInput'
import ImageUpload from './ImageUpload'
import { isQuickActionLabelSet } from './QuickActions'
import { useChat } from '../../context/ChatContext'
import './ChatWindow.css'

const TEXTAREA_MAX_HEIGHT = 120
const SINGLE_LINE_THRESHOLD = 44
const ORDER_HINT_PATTERN = /\b(add|order|cart|remove|checkout|buy)\b/i
const BUTTON_ONLY_PLACEHOLDER = 'Please select an option above'
const DEFAULT_PLACEHOLDER = 'Type your message...'

// True when the latest assistant message expects a widget interaction
// (date picker, time slots, pickup/delivery, confirm yes/no, the address
// map, ...) rather than free text - typing something else at that point is
// exactly what's produced crashes/confused state in the checkout and
// reservation flows before. Guest count is deliberately NOT gated here -
// it's a free-text numeric step validated server-side. The general_chat
// "quick action" suggestions (View Menu, Café Location, ...) are NOT gating
// either - those are just shortcuts, so free text stays enabled for them.
function isButtonOnlyStep(message) {
  if (!message || message.role !== 'assistant') return false
  if (message.awaitingAddressInput) return true
  if (message.datePickerOptions && message.datePickerOptions.length > 0) return true
  if (message.quickReplyOptions && message.quickReplyOptions.length > 0) {
    return !isQuickActionLabelSet(message.quickReplyOptions)
  }
  return false
}

export default function ChatWindow() {
  const { messages, isTyping, language, sendUserMessage, sendUserImage } = useChat()
  const [draft, setDraft] = useState('')
  const [isRecording, setIsRecording] = useState(false)
  const [isMultiline, setIsMultiline] = useState(false)
  const [attachedImage, setAttachedImage] = useState(null)
  const listRef = useRef(null)
  const inputRef = useRef(null)

  useEffect(() => {
    if (listRef.current) {
      listRef.current.scrollTop = listRef.current.scrollHeight
    }
  }, [messages, isTyping])

  useEffect(() => {
    return () => {
      if (attachedImage) URL.revokeObjectURL(attachedImage.previewUrl)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

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
    if (!text && !attachedImage) return

    if (attachedImage) {
      sendUserImage(attachedImage.file, text)
      URL.revokeObjectURL(attachedImage.previewUrl)
      setAttachedImage(null)
    } else {
      sendUserMessage(text)
    }
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

  function handleVoiceTranscript(transcript) {
    if (!transcript.trim()) return
    setDraft((prev) => (prev.trim() ? `${prev.trim()} ${transcript}` : transcript))
  }

  function handleImageSelect(file) {
    setAttachedImage((prev) => {
      if (prev) URL.revokeObjectURL(prev.previewUrl)
      return { file, previewUrl: URL.createObjectURL(file) }
    })
  }

  function handleRemoveAttachment() {
    setAttachedImage((prev) => {
      if (prev) URL.revokeObjectURL(prev.previewUrl)
      return null
    })
  }

  const inputBlocked = useMemo(() => isButtonOnlyStep(messages[messages.length - 1]), [messages])
  const canSend = !isTyping && !inputBlocked && (draft.trim().length > 0 || attachedImage !== null)

  const lastUserMessage = [...messages].reverse().find((msg) => msg.role === 'user')
  const typingHint = lastUserMessage && ORDER_HINT_PATTERN.test(lastUserMessage.text) ? 'order' : null

  return (
    <div className="chat-window">
      <div className="chat-messages" ref={listRef}>
        {messages.length === 0 && (
          <p className="chat-empty-state">No messages yet - say hello or ask about the menu!</p>
        )}
        {messages.map((msg, index) => (
          <MessageBubble
            key={msg.id}
            role={msg.role}
            text={msg.text}
            timestamp={msg.timestamp}
            imageUrl={msg.imageUrl}
            menuDisplay={msg.menuDisplay}
            suggestedItems={msg.suggestedItems}
            orderSummary={msg.orderSummary}
            quickReplyOptions={msg.quickReplyOptions}
            datePickerOptions={msg.datePickerOptions}
            paymentRequest={msg.paymentRequest}
            loyaltyCard={msg.loyaltyCard}
            locationCards={msg.locationCards}
            awaitingAddressInput={msg.awaitingAddressInput}
            status={msg.status}
            isLatest={index === messages.length - 1}
          />
        ))}
        <TypingIndicator show={isTyping} hint={typingHint} />
      </div>

      {!isRecording && (
        <AttachmentPreview previewUrl={attachedImage?.previewUrl} onRemove={handleRemoveAttachment} />
      )}

      <form className="chat-input-bar" onSubmit={handleFormSubmit}>
        {!isRecording && <ImageUpload onSelect={handleImageSelect} disabled={isTyping || inputBlocked} />}
        {!isRecording && (
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
        )}
        <VoiceInput
          language={language}
          onFinalTranscript={handleVoiceTranscript}
          disabled={isTyping || inputBlocked}
          onRecordingChange={setIsRecording}
        />
        {!isRecording && (
          <button className="chat-send-btn" type="submit" disabled={!canSend} aria-label="Send message">
            <span aria-hidden="true">&#10148;</span>
          </button>
        )}
      </form>
    </div>
  )
}

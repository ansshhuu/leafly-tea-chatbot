import { useChat } from '../../context/ChatContext'
import './QuickReplyOptions.css'

export default function QuickReplyOptions({ options, disabled = false }) {
  const { sendUserMessage, isTyping } = useChat()

  if (!options || options.length === 0) return null

  return (
    <div className="quick-reply-options" role="group" aria-label="Quick replies">
      {options.map((option) => (
        <button
          key={option}
          type="button"
          className="quick-reply-btn"
          onClick={() => sendUserMessage(option)}
          disabled={isTyping || disabled}
        >
          {option}
        </button>
      ))}
    </div>
  )
}

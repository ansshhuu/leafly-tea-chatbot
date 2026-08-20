import { Calendar, MapPin, Menu, Sparkles } from 'lucide-react'
import { useChat } from '../../context/ChatContext'
import './QuickActions.css'

export const QUICK_ACTION_LABELS = ['View Menu', 'Café Location', 'Book a Table', 'Events & Offers']

const ACTIONS = [
  { Icon: Menu, label: 'View Menu', message: 'Show me the menu' },
  { Icon: MapPin, label: 'Café Location', message: 'Where is the café located?' },
  { Icon: Calendar, label: 'Book a Table', message: "I'd like to book a table" },
  { Icon: Sparkles, label: 'Events & Offers', message: 'Do you have any events or offers?' },
]

export function isQuickActionLabelSet(options) {
  if (!options || options.length !== QUICK_ACTION_LABELS.length) return false
  const asSet = new Set(options)
  return QUICK_ACTION_LABELS.every((label) => asSet.has(label))
}

export default function QuickActions({ disabled = false }) {
  const { sendUserMessage, isTyping } = useChat()

  return (
    <div className="quick-actions" role="group" aria-label="Quick actions">
      {ACTIONS.map(({ Icon, label, message }) => (
        <button
          key={label}
          type="button"
          className="quick-action-btn"
          onClick={() => sendUserMessage(message)}
          disabled={isTyping || disabled}
        >
          <Icon className="quick-action-icon" size={16} strokeWidth={1.75} aria-hidden="true" />
          {label}
        </button>
      ))}
    </div>
  )
}

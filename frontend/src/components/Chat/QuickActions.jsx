import { Gift, Leaf, Sparkles } from 'lucide-react'
import { useChat } from '../../context/ChatContext'
import './QuickActions.css'

export const QUICK_ACTION_LABELS = ['View Products', 'Gift Hampers']

const ACTIONS = [
  { Icon: Leaf, label: 'View Products', message: 'Show me your teas' },
  { Icon: Gift, label: 'Gift Hampers', message: 'Do you have gift hampers?' },
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

import { useChat } from '../../context/ChatContext'
import './DatePicker.css'

const WEEKDAY_HEADERS = ['S', 'M', 'T', 'W', 'T', 'F', 'S']

function parseIsoDate(iso) {
  const [year, month, day] = iso.split('-').map(Number)
  return new Date(year, month - 1, day)
}

function toIsoDate(date) {
  const y = date.getFullYear()
  const m = String(date.getMonth() + 1).padStart(2, '0')
  const d = String(date.getDate()).padStart(2, '0')
  return `${y}-${m}-${d}`
}

export default function DatePicker({ options, disabled = false }) {
  const { sendUserMessage, isTyping } = useChat()

  if (!options || options.length === 0) return null

  const byDate = new Map(options.map((option) => [option.date, option]))
  const anchor = parseIsoDate(options[0].date)
  const year = anchor.getFullYear()
  const month = anchor.getMonth()
  const daysInMonth = new Date(year, month + 1, 0).getDate()
  const firstWeekday = new Date(year, month, 1).getDay()

  const cells = []
  for (let i = 0; i < firstWeekday; i++) cells.push(null)
  for (let day = 1; day <= daysInMonth; day++) cells.push(new Date(year, month, day))

  function handleClick(option) {
    if (!option.available || isTyping || disabled) return
    const asDate = parseIsoDate(option.date)
    const phrase = asDate.toLocaleDateString('en-US', { month: 'long', day: 'numeric', year: 'numeric' })
    sendUserMessage(phrase)
  }

  return (
    <div className="date-picker">
      <div className="date-picker-weekdays" aria-hidden="true">
        {WEEKDAY_HEADERS.map((label, i) => (
          <span key={i}>{label}</span>
        ))}
      </div>
      <div className="date-picker-grid" role="group" aria-label="Select a date">
        {cells.map((date, i) => {
          if (!date) {
            return <span key={`pad-${i}`} className="date-picker-cell date-picker-cell--pad" aria-hidden="true" />
          }

          const iso = toIsoDate(date)
          const option = byDate.get(iso)

          if (!option) {
            return (
              <span key={iso} className="date-picker-cell date-picker-cell--muted" aria-hidden="true">
                {date.getDate()}
              </span>
            )
          }

          return (
            <button
              key={iso}
              type="button"
              className={`date-picker-cell date-picker-cell--active ${iso === options[0].date ? 'date-picker-cell--today' : ''}`}
              onClick={() => handleClick(option)}
              disabled={!option.available || isTyping || disabled}
              aria-label={`${option.label}${option.available ? '' : ' - fully booked'}`}
            >
              {date.getDate()}
            </button>
          )
        })}
      </div>
    </div>
  )
}

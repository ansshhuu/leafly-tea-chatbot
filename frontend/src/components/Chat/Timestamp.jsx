function formatTime(isoString) {
  const date = new Date(isoString)
  return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
}

export default function Timestamp({ isoString }) {
  return <span className="timestamp">{formatTime(isoString)}</span>
}

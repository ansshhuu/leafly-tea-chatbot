export default function ReadReceipt({ status }) {
  if (!status) return null

  return (
    <span className={`read-receipt ${status === 'delivered' ? 'read-receipt--delivered' : ''}`} aria-hidden="true">
      {status === 'delivered' ? '✓✓' : '✓'}
    </span>
  )
}

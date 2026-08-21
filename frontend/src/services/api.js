const BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'

export async function checkHealth() {
  const res = await fetch(`${BASE_URL}/health`)
  if (!res.ok) throw new Error('Health check failed')
  return res.json()
}

export async function sendMessage(sessionId, message) {
  const body = { session_id: sessionId, message }

  const res = await fetch(`${BASE_URL}/api/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })

  if (!res.ok) {
    throw new Error(`Chat request failed (${res.status})`)
  }

  return res.json()
}

export async function fetchChatHistory(sessionId) {
  const res = await fetch(`${BASE_URL}/api/chat/history/${encodeURIComponent(sessionId)}`)
  if (!res.ok) {
    throw new Error(`Chat history request failed (${res.status})`)
  }
  return res.json()
}

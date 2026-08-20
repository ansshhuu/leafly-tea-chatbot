const BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'

export const MAX_IMAGE_BYTES = 5 * 1024 * 1024
export const ALLOWED_IMAGE_TYPES = ['image/jpeg', 'image/png']

export async function checkHealth() {
  const res = await fetch(`${BASE_URL}/health`)
  if (!res.ok) throw new Error('Health check failed')
  return res.json()
}

export async function fetchWelcome(coords) {
  const params = coords ? `?lat=${coords.lat}&lon=${coords.lon}` : ''
  const res = await fetch(`${BASE_URL}/api/chat/welcome${params}`)
  if (!res.ok) {
    throw new Error(`Welcome request failed (${res.status})`)
  }
  return res.json()
}

export async function sendMessage(sessionId, message, addressCoords) {
  const body = { session_id: sessionId, message }
  if (addressCoords && typeof addressCoords.lat === 'number' && typeof addressCoords.lon === 'number') {
    body.address_lat = addressCoords.lat
    body.address_lon = addressCoords.lon
  }

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

export async function fetchAddressSuggestions(query) {
  const res = await fetch(`${BASE_URL}/api/geocode/suggest?q=${encodeURIComponent(query)}`)
  if (!res.ok) {
    throw new Error(`Address suggest request failed (${res.status})`)
  }
  return res.json()
}

export async function fetchReverseGeocode(lat, lon) {
  const res = await fetch(`${BASE_URL}/api/geocode/reverse?lat=${lat}&lon=${lon}`)
  if (!res.ok) {
    throw new Error(`Reverse geocode request failed (${res.status})`)
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

export async function sendCartReminder(sessionId) {
  const res = await fetch(`${BASE_URL}/api/email/cart-reminder`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ session_id: sessionId }),
  })

  if (!res.ok) {
    throw new Error(`Cart reminder request failed (${res.status})`)
  }

  return res.json()
}

export async function sendImageMessage(sessionId, file, message) {
  const formData = new FormData()
  formData.append('session_id', sessionId)
  if (message) formData.append('message', message)
  formData.append('image', file)

  const res = await fetch(`${BASE_URL}/api/chat/image`, {
    method: 'POST',
    body: formData,
  })

  if (!res.ok) {
    throw new Error(`Image chat request failed (${res.status})`)
  }

  return res.json()
}

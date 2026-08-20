const DEFAULT_TIMEOUT_MS = 3000

// Resolves to {lat, lon} on success, or null on denial/unavailability/timeout
// - never rejects, so callers can just `await` it without a try/catch and
// fall back to cafe-location weather.
export function getUserCoordinates(timeoutMs = DEFAULT_TIMEOUT_MS) {
  return new Promise((resolve) => {
    if (typeof navigator === 'undefined' || !navigator.geolocation) {
      resolve(null)
      return
    }

    navigator.geolocation.getCurrentPosition(
      (position) => {
        resolve({ lat: position.coords.latitude, lon: position.coords.longitude })
      },
      () => resolve(null),
      { timeout: timeoutMs, maximumAge: 5 * 60 * 1000 }
    )
  })
}

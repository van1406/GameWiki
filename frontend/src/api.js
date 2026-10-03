// Thin API client. In dev, Vite proxies /api -> http://localhost:8000 (see vite.config.js).
const API_BASE = import.meta.env.VITE_API_BASE || '/api'

async function request(path, options = {}) {
  let response
  try {
    response = await fetch(`${API_BASE}${path}`, options)
  } catch {
    throw new Error('Cannot reach the server. Please make sure it is running and try again.')
  }

  let data = null
  try {
    data = await response.json()
  } catch {
    // no JSON body
  }

  if (!response.ok) {
    const detail = data?.detail
    const message =
      typeof detail === 'string'
        ? detail
        : detail
          ? JSON.stringify(detail)
          : `Request failed (HTTP ${response.status})`
    throw new Error(message)
  }
  return data
}

export function getGames() {
  return request('/games')
}

export function getHealth() {
  return request('/health')
}

export function askQuestion(game, question) {
  return request('/ask', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ game, question }),
  })
}

export function runIngest() {
  return request('/ingest', { method: 'POST' })
}

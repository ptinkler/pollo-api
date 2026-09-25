import { apiGet, apiPost, apiDelete } from './useApi'
import { useAuth } from './useAuth'

const enc = encodeURIComponent

// ── REST ─────────────────────────────────────────────────────────────
export const fetchChatStatus = () => apiGet('/api/chat/status')
export const fetchChatModels = (refresh = false) => apiGet(`/api/chat/models${refresh ? '?refresh=true' : ''}`)
export const fetchConversations = () => apiGet('/api/chat/conversations')
export const fetchConversation = (id) => apiGet(`/api/chat/conversations/${enc(id)}`)
export const createConversation = (data = {}) => apiPost('/api/chat/conversations', data)
export const deleteConversation = (id) => apiDelete(`/api/chat/conversations/${enc(id)}`)
export const fetchChatMessage = (id) => apiGet(`/api/chat/messages/${id}`)
export const cancelChatMessage = (id) => apiPost(`/api/chat/messages/${id}/cancel`)
export const fetchChatLibrary = () => apiGet('/api/chat/library')
export const deleteLibraryItem = (mediaId) => apiDelete(`/api/chat/library/${enc(mediaId)}`)

export async function renameConversation(id, title) {
  const res = await fetch(`/api/chat/conversations/${enc(id)}`, {
    method: 'PATCH',
    credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ title }),
  })
  if (!res.ok) throw new Error(`API error: ${res.status}`)
  return res.json()
}

export async function uploadChatAttachment(convId, file) {
  const form = new FormData()
  form.append('file', file)
  const res = await fetch(`/api/chat/conversations/${enc(convId)}/attachments`, {
    method: 'POST', credentials: 'same-origin', body: form,
  })
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw new Error(body.detail || `Upload failed: ${res.status}`)
  }
  return res.json()
}

export const chatMediaUrl = (convId, file) => `/api/chat/media/${enc(convId)}/${enc(file)}`

// ── Streaming turns ──────────────────────────────────────────────────

/**
 * POST a turn and feed each SSE event to `onEvent`. Resolves when the
 * stream ends. Aborting `signal` only stops listening — the server keeps
 * the turn running (use cancelChatMessage to actually stop it).
 */
export async function streamTurn(path, body, onEvent, signal) {
  const res = await fetch(path, {
    method: 'POST',
    credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
    body: JSON.stringify(body),
    signal,
  })
  if (res.status === 401) {
    useAuth().promptForKey()
    throw new Error('API key required')
  }
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail || `API error: ${res.status}`)
  }
  await readSSE(res.body, onEvent)
}

export async function readSSE(stream, onEvent) {
  const reader = stream.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  for (;;) {
    const { value, done } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    let sep
    while ((sep = buffer.indexOf('\n\n')) !== -1) {
      const block = buffer.slice(0, sep)
      buffer = buffer.slice(sep + 2)
      const data = block.split('\n')
        .filter(l => l.startsWith('data: '))
        .map(l => l.slice(6))
        .join('\n')
      if (data) onEvent(JSON.parse(data))
    }
  }
}

export const sendChatMessage = (convId, body, onEvent, signal) =>
  streamTurn(`/api/chat/conversations/${enc(convId)}/messages`, body, onEvent, signal)

export const retryChatMessage = (convId, body, onEvent, signal) =>
  streamTurn(`/api/chat/conversations/${enc(convId)}/retry`, body, onEvent, signal)

export const editChatMessage = (convId, body, onEvent, signal) =>
  streamTurn(`/api/chat/conversations/${enc(convId)}/edit`, body, onEvent, signal)

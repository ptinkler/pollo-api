import { apiGet, apiPost, apiPut, apiPatch, apiDelete, apiUpload } from './useApi'
import { useAuth } from './useAuth'

const enc = encodeURIComponent

// ── REST ─────────────────────────────────────────────────────────────
export const fetchChatStatus = () => apiGet('/api/chat/status')
export const fetchChatModels = (refresh = false) => apiGet(`/api/chat/models${refresh ? '?refresh=true' : ''}`)
export const fetchOpenRouterCredits = () => apiGet('/api/chat/credits')
export const fetchVeniceBalance = () => apiGet('/api/chat/venice-balance')
// Pinned + most recent ({ conversations, more }); with `q`, chats whose title or messages match (each with a `snippet`)
export const fetchConversations = (q = '') => apiGet(`/api/chat/conversations${q ? `?q=${enc(q)}` : ''}`)
// What a chat has cost: { usd, credits, inherited_usd, inherited_credits }
export const fetchConversationSpend = id => apiGet(`/api/chat/conversations/${enc(id)}/spend`)
export const fetchConversation = id => apiGet(`/api/chat/conversations/${enc(id)}`)
export const createConversation = (data = {}) => apiPost('/api/chat/conversations', data)
export const deleteConversation = id => apiDelete(`/api/chat/conversations/${enc(id)}`)
export const fetchChatMessage = id => apiGet(`/api/chat/messages/${id}`)
export const cancelChatMessage = id => apiPost(`/api/chat/messages/${id}/cancel`)
// Show the branch through this message (edits/retries are kept as sibling branches)
export const switchChatBranch = (convId, messageId) =>
  apiPost(`/api/chat/conversations/${enc(convId)}/branch`, { message_id: messageId })
// New chat from a prompt: the messages up to it, it and its reply — nothing after
export const forkConversation = (convId, messageId) =>
  apiPost(`/api/chat/conversations/${enc(convId)}/fork`, { message_id: messageId })
export const regenerateChatMedia = (messageId, mediaId, model = null) =>
  apiPost(`/api/chat/messages/${messageId}/media/${enc(mediaId)}/regenerate`, { model })
// Pinned images go to the image model as references with every new image on this branch
export const pinChatMedia = (messageId, mediaId, pinned) =>
  apiPost(`/api/chat/messages/${messageId}/media/${enc(mediaId)}/pin`, { pinned })
// Delete a prompt's turn (all versions of it and its replies); generated media moves to the library
export const deleteChatExchange = messageId => apiDelete(`/api/chat/messages/${messageId}`)
// What that would also remove: { other_versions, other_messages }
export const fetchDeleteInfo = messageId => apiGet(`/api/chat/messages/${messageId}/delete-info`)

// Custom instructions (saved, attachable per chat)
export const fetchInstructions = () => apiGet('/api/chat/instructions')
export const createInstruction = data => apiPost('/api/chat/instructions', data)
export const updateInstruction = (id, data) => apiPut(`/api/chat/instructions/${id}`, data)
export const deleteInstruction = id => apiDelete(`/api/chat/instructions/${id}`)

export const patchConversation = (id, data) => apiPatch(`/api/chat/conversations/${enc(id)}`, data)
export const uploadChatAttachment = (convId, file) =>
  apiUpload(`/api/chat/conversations/${enc(convId)}/attachments`, file)

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
      const data = block
        .split('\n')
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

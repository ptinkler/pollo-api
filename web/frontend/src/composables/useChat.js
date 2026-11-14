import { apiGet, apiPost, apiPut, apiPatch, apiDelete, apiUpload } from './useApi'
import { useAuth } from './useAuth'

const enc = encodeURIComponent

export const fetchChatStatus = () => apiGet('/api/chat/status')
export const fetchChatModels = (refresh = false) => apiGet(`/api/chat/models${refresh ? '?refresh=true' : ''}`)
export const fetchOpenRouterCredits = () => apiGet('/api/chat/credits')
export const fetchVeniceBalance = () => apiGet('/api/chat/venice-balance')
// Pinned + most recent ({ conversations, more }); with `q`, chats whose title or messages match (each with a `snippet`)
export const fetchConversations = (q = '') => apiGet(`/api/chat/conversations${q ? `?q=${enc(q)}` : ''}`)
// What a chat has cost: { usd, credits, inherited_usd, inherited_credits }
export const fetchConversationSpend = id => apiGet(`/api/chat/conversations/${enc(id)}/spend`)
// Pollo's official TTS voices: { voices: [{voiceId, voiceName, language, gender, ...}], total }
export const fetchAudioVoices = (params = '') => apiGet(`/api/chat/audio/voices${params}`)
export const fetchSpendBreakdown = days => apiGet(`/api/chat/spend/breakdown?days=${days}`)
export const estimateChatCost = data => apiPost('/api/chat/estimate', data)
export const enhanceChatPrompt = data => apiPost('/api/chat/enhance-prompt', data)
export const fetchConversation = id => apiGet(`/api/chat/conversations/${enc(id)}`)
// Newest image file per conversation id, for gallery cover thumbnails: { thumbs: {id: file} }
export const fetchConversationThumbs = ids => apiGet(`/api/chat/conversations/thumbs?ids=${enc(ids.join(','))}`)
export const createConversation = (data = {}) => apiPost('/api/chat/conversations', data)
export const deleteConversation = (id, { deleteMedia = true } = {}) =>
  apiDelete(`/api/chat/conversations/${enc(id)}?delete_media=${deleteMedia}`)
export const fetchChatMessage = id => apiGet(`/api/chat/messages/${id}`)
export const cancelChatMessage = id => apiPost(`/api/chat/messages/${id}/cancel`)
// Show the branch through this message (edits/retries are kept as sibling branches)
export const switchChatBranch = (convId, messageId) =>
  apiPost(`/api/chat/conversations/${enc(convId)}/branch`, { message_id: messageId })
// New chat from a prompt: the messages up to it, it and its reply — nothing after
export const forkConversation = (convId, messageId) =>
  apiPost(`/api/chat/conversations/${enc(convId)}/fork`, { message_id: messageId })
// Make this image/video again. `prompt` overrides the one it was made with,
// `edit` sends the picture itself back as the reference (change this image),
// and `replace` swaps it in place, keeping the old one as an earlier version.
export const regenerateChatMedia = (messageId, mediaId, { model = null, prompt, edit, replace } = {}) =>
  apiPost(`/api/chat/messages/${messageId}/media/${enc(mediaId)}/regenerate`, { model, prompt, edit, replace })
// Show one of a reply's wordings (0 = first); its pictures are untouched
export const showChatTextVersion = (messageId, index) =>
  apiPost(`/api/chat/messages/${messageId}/text-version`, { index })
// Make one of a card's pictures the real one (0 = first): the chat uses it from then on
export const showChatMediaVersion = (messageId, mediaId, index) =>
  apiPost(`/api/chat/messages/${messageId}/media/${enc(mediaId)}/version`, { index })
// Pinned images go to the image model as references with every new image on this branch
export const pinChatMedia = (messageId, mediaId, pinned) =>
  apiPost(`/api/chat/messages/${messageId}/media/${enc(mediaId)}/pin`, { pinned })
// Favourite (★) a generation: a bookmark that surfaces it in the Favourites gallery (images + videos)
export const favouriteChatMedia = (messageId, mediaId, favourite) =>
  apiPost(`/api/chat/messages/${messageId}/media/${enc(mediaId)}/favourite`, { favourite })
// In-flight (and tracked) generations across every thread — powers the queue dock.
// `known` = message ids to resolve even once they've left the pending set.
export const fetchActiveGenerations = (known = []) => apiPost('/api/chat/generations/active', { known })
// Every generated image/video across all threads, newest first (see /api/chat/library)
export const fetchChatLibrary = () => apiGet('/api/chat/library')
// Delete a prompt's turn (all versions of it and its replies); generated media moves to the library
export const deleteChatExchange = (messageId, { deleteMedia = false } = {}) =>
  apiDelete(`/api/chat/messages/${messageId}?delete_media=${deleteMedia}`)
// What that would also remove: { other_versions, other_messages }
export const fetchDeleteInfo = messageId => apiGet(`/api/chat/messages/${messageId}/delete-info`)

// Custom instructions: snippets, and groups that bundle them (attachable per chat)
export const fetchInstructions = () => apiGet('/api/chat/instructions')
export const createInstruction = data => apiPost('/api/chat/instructions', data)
export const updateInstruction = (id, data) => apiPut(`/api/chat/instructions/${id}`, data)
export const deleteInstruction = id => apiDelete(`/api/chat/instructions/${id}`)
export const createInstructionGroup = data => apiPost('/api/chat/instruction-groups', data)
export const updateInstructionGroup = (id, data) => apiPut(`/api/chat/instruction-groups/${id}`, data)
export const deleteInstructionGroup = id => apiDelete(`/api/chat/instruction-groups/${id}`)

// Spaces: chat-only groupings with their own default characters/instructions
export const fetchSpaces = () => apiGet('/api/chat/spaces')
export const createSpace = data => apiPost('/api/chat/spaces', data)
export const updateSpace = (id, data) => apiPut(`/api/chat/spaces/${id}`, data)
export const deleteSpace = id => apiDelete(`/api/chat/spaces/${id}`)

// Global defaults bucket (characters + instructions added to every new chat)
export const fetchSettings = () => apiGet('/api/chat/settings')
export const updateSettings = data => apiPut('/api/chat/settings', data)
// The text model that names new chats ('' / null = the chat's own model)
export const setTitleModel = title_model => apiPut('/api/chat/settings/title-model', { title_model })

export const patchConversation = (id, data) => apiPatch(`/api/chat/conversations/${enc(id)}`, data)

// ChatGPT exports in the server's imports folder, and the last import's progress: { folder, files, job }
export const fetchChatGptImport = () => apiGet('/api/chat/import/chatgpt')
// Start importing one of them in the background (only what's new since the last import)
export const startChatGptImport = file => apiPost('/api/chat/import/chatgpt', { file })
// Uploading an export into that folder, in chunks: start → { id, chunk_size }, then each chunk at its
// offset → { received }, and the last also → { file }
export const startChatGptUpload = (name, size) => apiPost('/api/chat/import/chatgpt/uploads', { name, size })
export function sendChatGptUploadChunk(id, offset, blob) {
  const form = new FormData()
  form.append('offset', String(offset))
  form.append('chunk', blob, 'chunk')
  return apiPost(`/api/chat/import/chatgpt/uploads/${enc(id)}`, form)
}
// Chats as a zip the Import dialog (here or on another server) reads back; no ids = every chat
export const chatExportUrl = (ids = []) => `/api/chat/export${ids.length ? `?ids=${enc(ids.join(','))}` : ''}`
// Every chat, for picking which to export: { chats: [{ id, title, kind, space, updated_at }] }
export const fetchExportableChats = () => apiGet('/api/chat/export/chats')
export const cancelChatGptUpload = id => apiDelete(`/api/chat/import/chatgpt/uploads/${enc(id)}`)
export const uploadChatAttachment = (convId, file) =>
  apiUpload(`/api/chat/conversations/${enc(convId)}/attachments`, file)

// A source video (e.g. Recast / motion models)
export const uploadChatVideoAttachment = (convId, file) =>
  apiUpload(`/api/chat/conversations/${enc(convId)}/attachments/video`, file)

// A lip-sync audio track
export const uploadChatAudioAttachment = (convId, file) =>
  apiUpload(`/api/chat/conversations/${enc(convId)}/attachments/audio`, file)

// Drop an uploaded-but-unsent attachment's file (the server keeps any still in use)
export const discardChatAttachment = (convId, file) =>
  apiDelete(`/api/chat/conversations/${enc(convId)}/attachments/${enc(file)}`)

export const chatMediaUrl = (convId, file) => `/api/chat/media/${enc(convId)}/${enc(file)}`
// A chat image scaled down for showing in the chat (the full file is for the lightbox)
export const chatMediaPreviewUrl = (convId, file) => `${chatMediaUrl(convId, file)}/preview`

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
    useAuth().promptLogin()
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

// Write a reply's words again, keeping the pictures it already made.
// Body: turn settings + message_id, and `instruction` to edit the words (empty = redo them)
export const rewordChatMessage = (convId, body, onEvent, signal) =>
  streamTurn(`/api/chat/conversations/${enc(convId)}/reword`, body, onEvent, signal)

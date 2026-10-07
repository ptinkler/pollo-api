import { apiGet, apiPost, apiPatch, apiDelete, apiUpload } from './useApi'

// Characters (see web/characters.py): a name, description and a few
// reference images, attachable to chats and generations. Ad-hoc ones belong
// to the chat they were made in until promoted to saved.
const enc = encodeURIComponent

export const fetchCharacters = ({ conversationId = null, includeAdhoc = false } = {}) => {
  const params = new URLSearchParams()
  if (conversationId) params.set('conversation_id', conversationId)
  if (includeAdhoc) params.set('include_adhoc', 'true')
  const qs = params.toString()
  return apiGet(`/api/characters${qs ? `?${qs}` : ''}`).then(r => r.characters)
}
export const createCharacter = (data) => apiPost('/api/characters', data)
export const updateCharacter = (id, data) => apiPatch(`/api/characters/${id}`, data)
export const deleteCharacter = (id) => apiDelete(`/api/characters/${id}`)
export const promoteCharacter = (id) => apiPost(`/api/characters/${id}/promote`)
export const uploadCharacterImage = (id, file) => apiUpload(`/api/characters/${id}/images`, file)
export const copyChatImageToCharacter = (id, conversationId, file) =>
  apiPost(`/api/characters/${id}/images/from-chat`, { conversation_id: conversationId, file })
export const copyGenerationImageToCharacter = (id, project, filename) =>
  apiPost(`/api/characters/${id}/images/from-generation`, { project, filename })

export const characterImageUrl = (id, file) => `/api/characters/${id}/images/${enc(file)}`
/** The character's main (first) image, or null. */
export const characterAvatar = (c) => (c?.images?.length ? characterImageUrl(c.id, c.images[0]) : null)

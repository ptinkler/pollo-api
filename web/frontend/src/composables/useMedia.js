import { reactive, computed } from 'vue'
import { apiGet, apiPost, apiDelete, apiUpload } from './useApi'

// The media library (see web/media.py): every upload and creation — library
// uploads, Generate projects' uploads/creations, chats' uploads/creations.
// Using an item somewhere copies it there (importMedia).
const enc = encodeURIComponent

export const fetchMedia = () => apiGet('/api/media').then(r => r.items)
export const uploadMedia = file => apiUpload('/api/media/upload', file)
export const deleteMedia = id => apiDelete(`/api/media/${enc(id)}`)

/** Chat generations a content filter blocked: { moderated, black } counts, and clearing them all. */
export const fetchBlockedCounts = () => apiGet('/api/media/blocked')
export const clearBlocked = () => apiPost('/api/media/blocked/clear', {})

/** Copy an image to a project ({ image_url: "local:…" }), a chat ({ file }) or a character (the character). */
export const importMedia = (mediaId, target) => apiPost('/api/media/import', { media_id: mediaId, ...target })

/** Where an item came from, for display. */
export function mediaOrigin(item) {
  if (item.origin === 'project') return item.project_name || item.project
  if (item.origin === 'chat') return item.conversation_title || 'Chat'
  if (item.origin === 'orphan') return item.conversation_title ? `${item.conversation_title} (orphaned)` : 'Orphaned'
  return 'Library'
}

/**
 * Filters over a list of media items (a ref): kind, source, origin and a
 * text search over prompt / name / where it's from.
 */
export function useMediaFilters(items, { kind = 'all', origin = 'all' } = {}) {
  const filters = reactive({ kind, source: 'all', origin, q: '' })
  const filtered = computed(() => {
    const q = filters.q.trim().toLowerCase()
    return items.value.filter(
      i =>
        (filters.kind === 'all' || i.kind === filters.kind) &&
        (filters.source === 'all' || i.source === filters.source) &&
        (filters.origin === 'all' || i.origin === filters.origin) &&
        (!q || [i.prompt, i.name, mediaOrigin(i)].some(s => s?.toLowerCase().includes(q))),
    )
  })
  return { filters, filtered }
}

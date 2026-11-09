import { computed, reactive, ref } from 'vue'
import {
  chatMediaUrl,
  chatMediaPreviewUrl,
  discardChatAttachment,
  uploadChatAttachment,
  uploadChatAudioAttachment,
  uploadChatVideoAttachment,
} from './useChat'
import { importMedia } from './useMedia'

export const MAX_ATTACHMENTS = 8

// Images attached to the next message: uploaded from the device, copied in
// from the media library, or already in the chat. Each is
// { key, file (once on the server), preview, uploading }.
export function useChatAttachments({ convId, ensureConversation, showToast, limit = () => MAX_ATTACHMENTS }) {
  const attachments = ref([])
  const images = () => attachments.value.filter(a => !a.video && !a.audio).length
  const room = () => Math.min(MAX_ATTACHMENTS - attachments.value.length, limit() - images())
  const files = computed(() => attachments.value.filter(a => a.file).map(a => a.file))
  const uploading = computed(() => attachments.value.some(a => a.uploading))

  // Why nothing more can be added: the model's own image limit, else the general cap
  const fullMessage = () =>
    limit() < MAX_ATTACHMENTS && images() >= limit()
      ? `This model takes ${limit()} image${limit() === 1 ? '' : 's'} — pick a reference-image (“Ref”) model for more`
      : `Up to ${MAX_ATTACHMENTS} attachments per message`

  function add(preview, file = null, video = false, audio = false) {
    const att = reactive({ key: Math.random().toString(36).slice(2), file, preview, video, audio, uploading: !file })
    attachments.value.push(att)
    return att
  }

  function remove(att) {
    if (att.preview.startsWith('blob:')) URL.revokeObjectURL(att.preview)
    attachments.value = attachments.value.filter(a => a !== att)
    // Removed before sending: don't leave the upload behind (no-op if still in use)
    if (att.file && convId.value) discardChatAttachment(convId.value, att.file).catch(() => {})
  }

  function clear() {
    attachments.value = []
  }

  // Each source becomes an attachment at once; `send(source, chatId)` puts it on the server
  async function attachEach(sources, preview, send, video = false, audio = false) {
    const single = video || audio // a video / audio rides singly, outside the image-count cap
    let id
    try {
      id = await ensureConversation()
    } catch (e) {
      return showToast(e.message, 'error')
    }
    if (!single && sources.length > room()) showToast(fullMessage(), 'error')
    for (const source of single ? sources : sources.slice(0, Math.max(room(), 0))) {
      const att = add(preview(source), null, video, audio)
      send(source, id)
        .then(r => {
          att.file = r.file
        })
        .catch(e => {
          showToast(e.message, 'error')
          remove(att)
        })
        .finally(() => {
          att.uploading = false
        })
    }
  }

  // Files from the device (picked, pasted or dropped): images, one source
  // video (the first mp4), and one lip-sync audio track (the first audio file).
  // A message carries a single video and a single audio.
  function addFiles(list) {
    const video = [...list].find(f => f.type === 'video/mp4')
    if (video && !attachments.value.some(a => a.video)) {
      attachEach(
        [video],
        f => URL.createObjectURL(f),
        (f, id) => uploadChatVideoAttachment(id, f),
        true,
      )
    }
    const audio = [...list].find(f => f.type.startsWith('audio/'))
    if (audio && !attachments.value.some(a => a.audio)) {
      attachEach(
        [audio],
        () => '',
        (f, id) => uploadChatAudioAttachment(id, f),
        false,
        true,
      )
    }
    const images = [...list].filter(f => f.type.startsWith('image/'))
    if (images.length) {
      attachEach(
        images,
        f => URL.createObjectURL(f),
        (f, id) => uploadChatAttachment(id, f),
      )
    }
  }

  // Items from the media library, copied into the chat
  function addFromLibrary(items) {
    attachEach(
      items,
      item => item.thumb_url || item.url,
      (item, id) => importMedia(item.id, { target: 'chat', conversation_id: id }),
    )
  }

  // An image already in this chat; false if there's no room for it
  // (`fromConv`: it lives in another thread, so copy it into this one)
  function addChatImage(file, fromConv = null) {
    if (/\.(mp4|webm|mov)$/i.test(file)) return false // a video isn't an image reference
    if (fromConv && fromConv !== convId.value) {
      if (room() < 1) {
        showToast(fullMessage(), 'error')
        return false
      }
      addFromLibrary([{ id: `chat:${fromConv}:${file}`, thumb_url: chatMediaPreviewUrl(fromConv, file) }])
      return true
    }
    if (attachments.value.some(a => a.file === file)) return true
    if (room() < 1) {
      showToast(fullMessage(), 'error')
      return false
    }
    add(chatMediaUrl(convId.value, file), file)
    return true
  }

  return { attachments, files, uploading, room, addFiles, addFromLibrary, addChatImage, remove, clear }
}

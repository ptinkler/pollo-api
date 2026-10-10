import { computed, reactive, ref } from 'vue'
import { chatMediaUrl, uploadChatAttachment } from './useChat'
import { importMedia } from './useMedia'

export const MAX_ATTACHMENTS = 8

// Images attached to the next message: uploaded from the device, copied in
// from the media library, or already in the chat. Each is
// { key, file (once on the server), preview, uploading }.
export function useChatAttachments({ convId, ensureConversation, showToast }) {
  const attachments = ref([])
  const room = () => MAX_ATTACHMENTS - attachments.value.length
  const files = computed(() => attachments.value.filter(a => a.file).map(a => a.file))
  const uploading = computed(() => attachments.value.some(a => a.uploading))

  function add(preview, file = null) {
    const att = reactive({ key: Math.random().toString(36).slice(2), file, preview, uploading: !file })
    attachments.value.push(att)
    return att
  }

  function remove(att) {
    if (att.preview.startsWith('blob:')) URL.revokeObjectURL(att.preview)
    attachments.value = attachments.value.filter(a => a !== att)
  }

  function clear() {
    attachments.value = []
  }

  // Each source becomes an attachment at once; `send(source, chatId)` puts it on the server
  async function attachEach(sources, preview, send) {
    let id
    try {
      id = await ensureConversation()
    } catch (e) {
      return showToast(e.message, 'error')
    }
    for (const source of sources.slice(0, room())) {
      const att = add(preview(source))
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

  // Files from the device (picked, pasted or dropped); only images are taken
  function addFiles(list) {
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
  function addChatImage(file) {
    if (attachments.value.some(a => a.file === file)) return true
    if (!room()) {
      showToast(`Up to ${MAX_ATTACHMENTS} attachments per message`, 'error')
      return false
    }
    add(chatMediaUrl(convId.value, file), file)
    return true
  }

  return { attachments, files, uploading, room, addFiles, addFromLibrary, addChatImage, remove, clear }
}

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
export function useChatAttachments({
  convId,
  ensureConversation,
  showToast,
  limit = () => MAX_ATTACHMENTS,
  videoLimit = () => 1,
  audioLimit = () => 1,
}) {
  const attachments = ref([])
  const images = () => attachments.value.filter(a => !a.video && !a.audio).length
  const videos = () => attachments.value.filter(a => a.video).length
  const audios = () => attachments.value.filter(a => a.audio).length
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

  // Files from the device (picked, pasted or dropped): images, source videos
  // and audio tracks. Most models take a single video + single audio; a
  // reference-to-video model takes several of each (up to its ref_mode caps,
  // via videoLimit / audioLimit).
  function addFiles(list) {
    const vids = [...list].filter(f => f.type === 'video/mp4').slice(0, Math.max(videoLimit() - videos(), 0))
    if (vids.length) {
      attachEach(
        vids,
        f => URL.createObjectURL(f),
        (f, id) => uploadChatVideoAttachment(id, f),
        true,
      )
    }
    const auds = [...list].filter(f => f.type.startsWith('audio/')).slice(0, Math.max(audioLimit() - audios(), 0))
    if (auds.length) {
      attachEach(
        auds,
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

  // Items from the media library, copied into the chat — each with its kind, so
  // a picked video imports as a video reference, not an image.
  function addFromLibrary(items) {
    for (const item of items) {
      // A video needs a playable URL for the <video> thumbnail; an image uses its thumb.
      const preview = item.kind === 'video' ? item.url || item.thumb_url : item.thumb_url || item.url
      attachEach(
        [item],
        () => preview || '',
        (it, id) => importMedia(it.id, { target: 'chat', conversation_id: id }),
        item.kind === 'video',
        item.kind === 'audio',
      )
    }
  }

  // Re-attach an existing media file by kind (image/video/audio) — used to put
  // a past generation's references back when you "use settings". Same thread:
  // reference it directly; another thread: import a copy with the right kind.
  function addChatMedia(file, kind = 'image', fromConv = null) {
    const video = kind === 'video'
    const audio = kind === 'audio'
    if (fromConv && fromConv !== convId.value) {
      attachEach(
        [{ id: `chat:${fromConv}:${file}`, thumb: chatMediaPreviewUrl(fromConv, file) }],
        s => s.thumb,
        (s, id) => importMedia(s.id, { target: 'chat', conversation_id: id }),
        video,
        audio,
      )
      return true
    }
    if (attachments.value.some(a => a.file === file)) return true
    add(audio ? '' : chatMediaUrl(convId.value, file), file, video, audio)
    return true
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

  return { attachments, files, uploading, room, addFiles, addFromLibrary, addChatImage, addChatMedia, remove, clear }
}

import { computed, reactive, ref } from 'vue'
import { patchConversation } from './useChat'
import { chatImageModelTakesCharacters, fetchCharacters } from './useCharacters'

// Replace the item with the same id in a list, or add it
export function upsert(list, item) {
  const i = list.findIndex(x => x.id === item.id)
  if (i === -1) list.push(item)
  else list.splice(i, 1, item)
}

// Why the current mode and models can't use characters, or null if they can
// (mirrors _characters_usable in web/chat.py). Unknown models (catalogue still
// loading) count as able, like on the server.
function characterBlocker({ mode, selected, textInfo, imageInfo, videoInfo }) {
  if (mode === 'text') return null
  if (mode === 'video') {
    // Only video models that take reference images (Venice refs→video, motion control)
    return videoInfo && (videoInfo.reference_images || videoInfo.family === 'motion')
      ? null
      : "This video model doesn't take reference images, so it can't use characters."
  }
  if (!selected.image) return 'Pick an image model to use characters.'
  if (imageInfo && !chatImageModelTakesCharacters(imageInfo)) {
    return `${imageInfo.name} can't take reference images, so it can't use characters.`
  }
  if (mode === 'auto' && textInfo && !textInfo.supports_tools) {
    return `${textInfo.name} can't call tools, so Auto mode can't use characters.`
  }
  return null
}

// Characters for the open chat: every saved one plus the chat's own (ad
// hoc) ones, which are attached, and the editor's state. `settings`: the
// composer settings (mode and model picks decide whether characters are used).
export function useChatCharacters({ convId, settings, ensureConversation, showToast }) {
  const characters = ref([])
  const characterIds = ref([]) // attached to this chat (or the next new one)
  const charEditor = reactive({ open: false, character: null, conversationId: null, seed: [] })
  const attachedCharacters = computed(() =>
    characterIds.value.map(id => characters.value.find(c => c.id === id)).filter(Boolean),
  )
  const characterNames = computed(() => attachedCharacters.value.map(c => c.name).join(', '))
  // When they can't be used, attached characters stay attached but unused
  const characterSupport = computed(() => {
    const reason = characterBlocker({
      mode: settings.mode.value,
      selected: settings.selected,
      textInfo: settings.textInfo.value,
      imageInfo: settings.imageInfo.value,
      videoInfo: settings.videoInfo.value,
    })
    return reason ? { ok: false, reason } : { ok: true }
  })

  async function loadCharacters() {
    try {
      characters.value = await fetchCharacters({ conversationId: convId.value })
    } catch {
      /* 401 handled by auth prompt */
    }
  }

  async function setCharacters(ids) {
    characterIds.value = ids
    if (!convId.value) return // new chats get them on creation
    try {
      await patchConversation(convId.value, { character_ids: ids })
    } catch (e) {
      showToast(`Couldn't update characters: ${e.message}`, 'error')
    }
  }

  function editCharacter(c) {
    Object.assign(charEditor, { open: true, character: c, conversationId: null, seed: [] })
  }

  // Characters made in a chat belong to it (ad hoc) until saved
  async function newCharacter(seed = []) {
    let id
    try {
      id = await ensureConversation()
    } catch (e) {
      return showToast(e.message, 'error')
    }
    Object.assign(charEditor, { open: true, character: null, conversationId: id, seed })
  }

  // The chat model used (or made) some: they're attached now
  function onCharactersUsed(used, ids) {
    for (const c of used) upsert(characters.value, c)
    characterIds.value = ids
  }

  function onCharacterSaved(c) {
    upsert(characters.value, c)
    if (charEditor.character?.id === c.id) charEditor.character = c
    // Made here: the server attached it to this chat
    if (c.conversation_id === convId.value && !characterIds.value.includes(c.id)) {
      characterIds.value = [...characterIds.value, c.id]
    }
  }

  function onCharacterDeleted(id) {
    characters.value = characters.value.filter(c => c.id !== id)
    characterIds.value = characterIds.value.filter(x => x !== id) // the server detaches it too
  }

  return {
    characters,
    characterIds,
    charEditor,
    attachedCharacters,
    characterNames,
    characterSupport,
    loadCharacters,
    setCharacters,
    editCharacter,
    newCharacter,
    onCharactersUsed,
    onCharacterSaved,
    onCharacterDeleted,
  }
}

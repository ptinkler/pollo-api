<script setup>
import { ref, reactive, computed, watch, nextTick, onMounted, onBeforeUnmount, inject, provide } from 'vue'
import { useRoute, useRouter, RouterLink } from 'vue-router'
import { useAuth } from '../composables/useAuth'
import { useSessionCredits } from '../composables/useSessionCredits'
import ModelPicker from '../components/chat/ModelPicker.vue'
import ChatMessage from '../components/chat/ChatMessage.vue'
import InstructionsDialog from '../components/chat/InstructionsDialog.vue'
import CharacterPicker from '../components/characters/CharacterPicker.vue'
import CharacterEditor from '../components/characters/CharacterEditor.vue'
import { fetchCharacters, chatImageModelTakesCharacters } from '../composables/useCharacters'
import { importMedia } from '../composables/useMedia'
import MediaPicker from '../components/media/MediaPicker.vue'
import {
  fetchChatStatus, fetchChatModels, fetchConversations, fetchConversation,
  createConversation, deleteConversation, fetchChatMessage,
  cancelChatMessage, uploadChatAttachment, chatMediaUrl, sendChatMessage, retryChatMessage,
  editChatMessage, switchChatBranch, fetchOpenRouterCredits, fetchVeniceBalance, regenerateChatMedia, pinChatMedia, deleteChatExchange, fetchDeleteInfo, fetchInstructions, patchConversation,
} from '../composables/useChat'

const route = useRoute()
const router = useRouter()
const showToast = inject('showToast', () => {})
const { hasKey, showKeyModal } = useAuth()

const MODES = [
  { id: 'auto', label: 'Auto', icon: '✦', hint: 'Chat model decides when to make images or videos' },
  { id: 'text', label: 'Chat', icon: '💬', hint: 'Text replies only' },
  { id: 'image', label: 'Image', icon: '🖼', hint: 'Send the prompt straight to the image model' },
  { id: 'video', label: 'Video', icon: '🎬', hint: 'Send the prompt (and image) straight to the video model' },
]
const DEFAULT_RATIOS = ['1:1', '16:9', '9:16', '4:3', '3:4', '3:2', '2:3', '21:9']
// First id containing one of these wins when nothing is remembered yet
const PREFERRED = {
  text: ['anthropic/claude-sonnet', 'google/gemini', 'openai/gpt'],
  image: ['gemini', 'seedream', 'flux', 'gpt-image'],
  video: ['veo', 'seedance', 'wan', 'sora'],
}
const STORE_KEY = 'chat.prefs'
// Memory slider stops: how many past messages the chat model gets (null = all)
const MEMORY_STEPS = [2, 4, 6, 10, 14, 20, 30, 40, 60, 80, 100, null]
const DEFAULT_MEMORY = 20
// Image slider stops: how many recent chat images go with each request (null = all)
const IMAGE_STEPS = [0, 1, 2, 3, 4, 6, 8, 10, 12, 16, 20, null]
const DEFAULT_IMAGES = 6   // mirrors DEFAULT_IMAGE_LIMIT in web/chat.py

// ── Persistent prefs (per browser) ───────────────────────────────────
function loadPrefs() {
  try { return JSON.parse(localStorage.getItem(STORE_KEY)) || {} } catch { return {} }
}
const prefs = loadPrefs()
const selected = reactive({
  text: prefs.text || '',
  image: prefs.image ?? '',
  video: prefs.video ?? '',
})
const mode = ref(prefs.mode || 'auto')
const memoryIndex = ref((() => {
  const i = MEMORY_STEPS.indexOf('memory' in prefs ? prefs.memory : DEFAULT_MEMORY)
  return i === -1 ? MEMORY_STEPS.indexOf(DEFAULT_MEMORY) : i
})())
const historyLimit = computed(() => MEMORY_STEPS[memoryIndex.value])
const imageIndex = ref((() => {
  const i = IMAGE_STEPS.indexOf('images' in prefs ? prefs.images : DEFAULT_IMAGES)
  return i === -1 ? IMAGE_STEPS.indexOf(DEFAULT_IMAGES) : i
})())
const imageLimit = computed(() => IMAGE_STEPS[imageIndex.value])
// Composer settings for generated media, used in every mode (Auto too).
// '' = let the chat model choose (Auto), else the media model's default.
const imageOpts = reactive({ aspect_ratio: '', resolution: '', ...prefs.imageOpts })
const videoOpts = reactive({ aspect_ratio: '', resolution: '', duration: '', generate_audio: true, ...prefs.videoOpts })

watch([() => ({ ...selected }), mode, memoryIndex, imageIndex, () => ({ ...imageOpts }), () => ({ ...videoOpts })], () => {
  try {
    localStorage.setItem(STORE_KEY, JSON.stringify({
      ...selected, mode: mode.value, memory: historyLimit.value, images: imageLimit.value,
      imageOpts: { ...imageOpts }, videoOpts: { ...videoOpts },
    }))
  } catch { /* storage unavailable */ }
}, { deep: true })

// ── Server state ─────────────────────────────────────────────────────
const configured = ref(true)
const providers = reactive({ openrouter: true, venice: false })   // which API keys the server has
const models = reactive({ text: [], image: [], video: [] })
provide('chatModels', models)   // for "Try another model" on failed media
const modelsLoading = ref(true)
const conversations = ref([])
const conversation = ref(null)
const messages = ref([])
const loadingConv = ref(false)

const convId = computed(() => route.params.id || null)

// ── Composer state ───────────────────────────────────────────────────
const draft = ref('')
const attachments = ref([])   // { key, file?, preview, uploading, error }
const sending = ref(false)
const streamingId = ref(null)
const textarea = ref(null)
const scroller = ref(null)
const messagesEl = ref(null)
const dragging = ref(false)
const sidebarOpen = ref(false)
const lightbox = ref(null)
let abort = null
let skipLoadFor = null

// What the slider means for this chat: the new prompt plus earlier messages
const memoryHint = computed(() => {
  const total = messages.value.length + 1
  const limit = historyLimit.value
  const n = imageLimit.value
  const imgs = n === null ? 'every image' : n === 0 ? 'no images' : `the ${n === 1 ? 'latest image' : `${n} most recent images`}`
  if (!limit || limit >= total) {
    return messages.value.length
      ? `Sending the whole chat (${total} messages) plus ${imgs}.`
      : `Sends up to ${limit ?? 'all'} messages plus ${imgs}.`
  }
  const dropped = total - limit
  return `Sending the last ${limit} of ${total} messages plus ${imgs}; the oldest ${dropped === 1 ? 'one is' : `${dropped} are`} left out.`
})

const currentMode = computed(() => MODES.find(m => m.id === mode.value) || MODES[0])

function cycleMode() {
  const i = MODES.findIndex(m => m.id === mode.value)
  mode.value = MODES[(i + 1) % MODES.length].id
}

function openConversation(id) {
  sidebarOpen.value = false
  router.push({ name: 'chat-conversation', params: { id } })
}

const textInfo = computed(() => models.text.find(m => m.id === selected.text))
const imageInfo = computed(() => models.image.find(m => m.id === selected.image))
const videoInfo = computed(() => models.video.find(m => m.id === selected.video))

const ratiosOf = (info) => (info?.aspect_ratios?.length ? info.aspect_ratios : DEFAULT_RATIOS)
const imageRatioOptions = computed(() => ratiosOf(imageInfo.value))
const imageResOptions = computed(() => imageInfo.value?.resolutions || [])
const videoRatioOptions = computed(() => ratiosOf(videoInfo.value))
const videoResOptions = computed(() => videoInfo.value?.resolutions || [])
const durationOptions = computed(() => videoInfo.value?.durations || [])
const showImageOpts = computed(() => !!selected.image && (mode.value === 'auto' || mode.value === 'image'))
const showVideoOpts = computed(() => !!selected.video && (mode.value === 'auto' || mode.value === 'video'))

// A newly picked model may not offer the old picks — fall back to auto/default
function dropUnsupported(opts, ratios, resolutions, durations = null) {
  if (opts.aspect_ratio && !ratios.includes(opts.aspect_ratio)) opts.aspect_ratio = ''
  if (opts.resolution && !resolutions.includes(opts.resolution)) opts.resolution = ''
  if (durations && opts.duration && !durations.includes(Number(opts.duration))) opts.duration = ''
}
watch(imageInfo, (info) => { if (info) dropUnsupported(imageOpts, imageRatioOptions.value, imageResOptions.value) })
watch(videoInfo, (info) => {
  if (info) dropUnsupported(videoOpts, videoRatioOptions.value, videoResOptions.value, durationOptions.value)
})

const modeWarning = computed(() => {
  if (mode.value === 'image' && !selected.image) return 'Pick an image model to use Image mode.'
  if (mode.value === 'video' && !selected.video) return 'Pick a video model to use Video mode.'
  if (mode.value === 'image' && attachments.value.length && imageInfo.value
      && !imageInfo.value.input_modalities?.includes('image'))
    return `${imageInfo.value.name} can't take reference images — pick one tagged “edits” or “context” to use the attached image.`
  if (mode.value === 'auto' && textInfo.value && !textInfo.value.supports_tools)
    return `${textInfo.value.name} can't call tools, so Auto mode will only chat. Use Image/Video mode, or pick a model tagged “tools”.`
  if (attachments.value.length && textInfo.value && !textInfo.value.input_modalities?.includes('image') && ['auto', 'text'].includes(mode.value))
    return `${textInfo.value.name} can't see images; it will only know you attached one.`
  return ''
})

const canSend = computed(() =>
  !sending.value &&
  (draft.value.trim() || attachments.value.some(a => a.file)) &&
  !attachments.value.some(a => a.uploading) &&
  (mode.value === 'image' ? selected.image : mode.value === 'video' ? selected.video : selected.text),
)

// Images pinned as references on the shown branch (the server uses the same set)
const pinned = computed(() => messages.value.flatMap(m =>
  (m.media || []).filter(i => i.pinned && i.kind === 'image').map(i => ({ msg: m, mediaId: i.id }))))

const lastAssistantId = computed(() => {
  const last = messages.value[messages.value.length - 1]
  return last?.role === 'assistant' ? last.id : null
})

// ── Loading ──────────────────────────────────────────────────────────
function pickDefault(kind) {
  const list = models[kind]
  if (!list.length) return ''
  for (const needle of PREFERRED[kind]) {
    const hit = list.find(m => m.id.includes(needle) && (kind !== 'text' || m.supports_tools))
    if (hit) return hit.id
  }
  return list[0].id
}

async function loadModels(refresh = false) {
  modelsLoading.value = true
  try {
    const data = await fetchChatModels(refresh)
    models.text = data.text || []
    models.image = data.image || []
    models.video = data.video || []
    for (const [kind, err] of Object.entries(data.errors || {})) {
      showToast(`Couldn't load ${kind} models: ${err}`, 'error')
    }
    if (!selected.text) selected.text = pickDefault('text')
    // '' is a deliberate "None" once the user has picked; only default on first run
    if (!('image' in prefs)) selected.image = pickDefault('image')
    if (!('video' in prefs)) selected.video = pickDefault('video')
  } catch (e) {
    showToast(`Couldn't load models: ${e.message}`, 'error')
  } finally {
    modelsLoading.value = false
  }
}

// ── Custom instructions ──────────────────────────────────────────────
const instructions = ref([])
const instructionId = ref(null)       // attached to this chat (or the next new one)
const instructionsOpen = ref(false)
const defaultInstructionId = () => instructions.value.find(i => i.is_default)?.id ?? null
const attachedInstruction = computed(() => instructions.value.find(i => i.id === instructionId.value))

async function loadInstructions() {
  try {
    instructions.value = (await fetchInstructions()).instructions
    if (!convId.value) instructionId.value = defaultInstructionId()
  } catch { /* 401 handled by auth prompt */ }
}

// Picking from the sidebar: saved on the chat right away (new chats get it on creation)
async function setInstruction(id) {
  instructionId.value = id
  if (!convId.value) return
  try {
    const updated = await patchConversation(convId.value, { instruction_id: id })
    if (conversation.value) conversation.value.instruction_id = updated.instruction_id
  } catch (e) {
    showToast(`Couldn't attach instructions: ${e.message}`, 'error')
  }
}

async function onInstructionsChanged({ saved, deleted }) {
  await loadInstructions()
  if (deleted && instructionId.value === deleted) instructionId.value = null
  // Saving from the dialog attaches it here if nothing was attached yet
  if (saved && instructionId.value == null) setInstruction(saved.id)
}

// ── Characters ───────────────────────────────────────────────────────
const characters = ref([])          // saved ones plus this chat's ad-hoc ones
const characterIds = ref([])        // attached to this chat (or the next new one)
const charEditor = reactive({ open: false, character: null, conversationId: null, seed: [] })
const attachedCharacters = computed(() =>
  characterIds.value.map(id => characters.value.find(c => c.id === id)).filter(Boolean))

// Whether the current mode + models can use characters (mirrors _characters_usable
// in web/chat.py). When they can't, attached ones stay attached but unused.
// Unknown models (catalogue still loading) count as able, like on the server.
const characterSupport = computed(() => {
  if (mode.value === 'text') return { ok: true }
  if (mode.value === 'video') {
    // Only video models that take reference images (Venice refs→video, motion control)
    const v = videoInfo.value
    return v && (v.reference_images || v.family === 'motion')
      ? { ok: true }
      : { ok: false, reason: "This video model doesn't take reference images, so it can't use characters." }
  }
  if (!selected.image) return { ok: false, reason: 'Pick an image model to use characters.' }
  if (imageInfo.value && !chatImageModelTakesCharacters(imageInfo.value)) {
    return { ok: false, reason: `${imageInfo.value.name} can't take reference images, so it can't use characters.` }
  }
  if (mode.value === 'auto' && textInfo.value && !textInfo.value.supports_tools) {
    return { ok: false, reason: `${textInfo.value.name} can't call tools, so Auto mode can't use characters.` }
  }
  return { ok: true }
})

async function loadCharacters() {
  try {
    characters.value = await fetchCharacters({ conversationId: convId.value })
  } catch { /* 401 handled by auth prompt */ }
}

async function setCharacters(ids) {
  characterIds.value = ids
  if (!convId.value) return   // new chats get them on creation
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

function characterFromImage(file) {
  lightbox.value = null
  newCharacter([{ kind: 'chat', conversationId: convId.value, file, preview: chatMediaUrl(convId.value, file) }])
}

function onCharacterSaved(c) {
  const i = characters.value.findIndex(x => x.id === c.id)
  if (i === -1) characters.value.push(c)
  else characters.value.splice(i, 1, c)
  if (charEditor.character?.id === c.id) charEditor.character = c
  // Made here: the server attached it to this chat
  if (c.conversation_id === convId.value && !characterIds.value.includes(c.id)) {
    characterIds.value = [...characterIds.value, c.id]
  }
}

function onCharacterDeleted(id) {
  characters.value = characters.value.filter(c => c.id !== id)
  characterIds.value = characterIds.value.filter(x => x !== id)   // the server detaches it too
}

async function loadConversations() {
  try {
    conversations.value = (await fetchConversations()).conversations
  } catch { /* shown elsewhere via 401 prompt */ }
}

async function loadConversation(id) {
  stopPolling()
  loadCharacters()
  if (!id) {
    conversation.value = null
    messages.value = []
    instructionId.value = defaultInstructionId()
    characterIds.value = []
    return
  }
  loadingConv.value = true
  try {
    const data = await fetchConversation(id)
    conversation.value = data.conversation
    messages.value = data.messages
    const c = data.conversation
    if (c.text_model) selected.text = c.text_model
    if (c.image_model) selected.image = c.image_model
    if (c.video_model) selected.video = c.video_model
    instructionId.value = c.instruction_id ?? null
    characterIds.value = c.character_ids || []
    document.title = `${c.title} — Chat`
    scrollToBottom(true)
    ensurePolling()
  } catch (e) {
    showToast(`Couldn't open chat: ${e.message}`, 'error')
    router.replace({ name: 'chat' })
  } finally {
    loadingConv.value = false
  }
}

watch(convId, (id) => {
  if (id && id === skipLoadFor) {
    skipLoadFor = null
    return
  }
  abort?.abort()
  attachments.value = []
  loadConversation(id)
})

// ── Conversations ────────────────────────────────────────────────────
async function ensureConversation() {
  if (convId.value) return convId.value
  const conv = await createConversation({
    text_model: selected.text || null,
    image_model: selected.image || null,
    video_model: selected.video || null,
    instruction_id: instructionId.value,   // explicit, so "None" sticks
    character_ids: characterIds.value,
  })
  conversation.value = conv
  conversations.value = [conv, ...conversations.value]
  skipLoadFor = conv.id
  await router.replace({ name: 'chat-conversation', params: { id: conv.id } })
  return conv.id
}

function newChat() {
  sidebarOpen.value = false
  // From a conversation *or* the Library — anywhere but the blank chat itself
  if (route.name !== 'chat') router.push({ name: 'chat' })
  draft.value = ''
  nextTick(() => textarea.value?.focus())
}

async function removeConversation(c) {
  if (!confirm(`Delete “${c.title}” and its images/videos?`)) return
  try {
    await deleteConversation(c.id)
    conversations.value = conversations.value.filter(x => x.id !== c.id)
    if (c.id === convId.value) router.push({ name: 'chat' })
  } catch (e) {
    showToast(`Delete failed: ${e.message}`, 'error')
  }
}

async function rename(c) {
  const title = prompt('Rename chat', c.title)
  if (!title || title === c.title) return
  try {
    const updated = await patchConversation(c.id, { title })
    c.title = updated.title
    if (conversation.value?.id === c.id) conversation.value.title = updated.title
  } catch (e) {
    showToast(`Rename failed: ${e.message}`, 'error')
  }
}

// ── Attachments ──────────────────────────────────────────────────────
async function addFiles(files) {
  const images = [...files].filter(f => f.type.startsWith('image/'))
  if (!images.length) return
  let id
  try {
    id = await ensureConversation()
  } catch (e) {
    return showToast(e.message, 'error')
  }
  for (const f of images.slice(0, 8 - attachments.value.length)) {
    const att = reactive({ key: Math.random().toString(36).slice(2), file: null, preview: URL.createObjectURL(f), uploading: true })
    attachments.value.push(att)
    uploadChatAttachment(id, f)
      .then(r => { att.file = r.file })
      .catch(e => {
        showToast(e.message, 'error')
        removeAttachment(att)
      })
      .finally(() => { att.uploading = false })
  }
}

// Attach images from the media library (copied into this chat)
const libraryOpen = ref(false)

async function attachFromLibrary(items) {
  let id
  try {
    id = await ensureConversation()
  } catch (e) {
    return showToast(e.message, 'error')
  }
  for (const item of items.slice(0, 8 - attachments.value.length)) {
    const att = reactive({ key: Math.random().toString(36).slice(2), file: null, preview: item.thumb_url || item.url, uploading: true })
    attachments.value.push(att)
    importMedia(item.id, { target: 'chat', conversation_id: id })
      .then(r => { att.file = r.file })
      .catch(e => {
        showToast(e.message, 'error')
        attachments.value = attachments.value.filter(a => a !== att)
      })
      .finally(() => { att.uploading = false })
  }
}

// "Picture / video from this image": attach an image already in this chat
// (generated or uploaded — however far up) and switch to Image or Video
// mode. Being attached to the new message also makes it the latest image,
// so Auto mode uses it too if the user switches back.
function useImage({ file, mode: target }) {
  lightbox.value = null
  if (!attachments.value.some(a => a.file === file)) {
    if (attachments.value.length >= 8) return showToast('Up to 8 attachments per message', 'error')
    attachments.value.push(reactive({
      key: Math.random().toString(36).slice(2), file, preview: chatMediaUrl(convId.value, file), uploading: false,
    }))
  }
  mode.value = target
  nextTick(() => textarea.value?.focus())
}

// "Picture / video from this reply": the reply (or the selected part) becomes
// the prompt, editable before sending. Anything already typed is kept.
function useText({ text, mode: target }) {
  if (!text) return
  draft.value = draft.value.trim() ? `${draft.value.trim()}\n\n${text}` : text
  mode.value = target
  autosize()
  nextTick(() => {
    textarea.value?.focus()
    textarea.value?.setSelectionRange(draft.value.length, draft.value.length)
  })
}

function removeAttachment(att) {
  URL.revokeObjectURL(att.preview)
  attachments.value = attachments.value.filter(a => a !== att)
}

function onPaste(e) {
  const files = [...(e.clipboardData?.files || [])]
  if (files.some(f => f.type.startsWith('image/'))) {
    e.preventDefault()
    addFiles(files)
  }
}

function onDrop(e) {
  dragging.value = false
  addFiles(e.dataTransfer?.files || [])
}

// ── Sending ──────────────────────────────────────────────────────────
// Retries and edits run in the mode selected now, like a new message
function turnSettings() {
  const body = {
    mode: mode.value,
    history_limit: historyLimit.value,
    image_limit: imageLimit.value,
    text_model: selected.text || null,
    image_model: selected.image || null,
    video_model: selected.video || null,
  }
  body.image_options = {
    aspect_ratio: imageOpts.aspect_ratio || null,
    resolution: imageOpts.resolution || null,
  }
  body.video_options = {
    aspect_ratio: videoOpts.aspect_ratio || null,
    resolution: videoOpts.resolution || null,
    duration: videoOpts.duration ? Number(videoOpts.duration) : null,
    generate_audio: videoInfo.value?.generate_audio ? videoOpts.generate_audio : null,
  }
  return body
}

function handleEvent(ev, tempUser) {
  const idx = (id) => messages.value.findIndex(m => m.id === id)
  switch (ev.type) {
    case 'start': {
      if (ev.user_message) {
        // New message: swap out the optimistic copy. Edit: refresh it in place.
        const i = tempUser ? messages.value.indexOf(tempUser) : idx(ev.user_message.id)
        if (i !== -1) messages.value.splice(i, 1, ev.user_message)
      }
      messages.value.push(ev.assistant_message)
      streamingId.value = ev.assistant_message.id
      scrollToBottom(true)
      break
    }
    case 'delta': {
      const m = messages.value[idx(streamingId.value)]
      if (m) m.content += ev.text
      scrollToBottom()
      break
    }
    case 'media': {
      const m = messages.value[idx(ev.message_id)]
      if (!m) break
      const media = m.media || (m.media = [])
      const j = media.findIndex(x => x.id === ev.item.id)
      if (j === -1) media.push(ev.item)
      else media.splice(j, 1, ev.item)
      scrollToBottom()
      break
    }
    case 'characters': {
      // The chat model used (or created) a character: it's attached now
      for (const c of ev.characters) {
        const i = characters.value.findIndex(x => x.id === c.id)
        if (i === -1) characters.value.push(c)
        else characters.value.splice(i, 1, c)
      }
      characterIds.value = ev.character_ids
      break
    }
    case 'title': {
      if (conversation.value) conversation.value.title = ev.title
      const c = conversations.value.find(x => x.id === convId.value)
      if (c) c.title = ev.title
      document.title = `${ev.title} — Chat`
      break
    }
    case 'done': {
      const i = idx(streamingId.value)
      if (i !== -1 && ev.message) messages.value.splice(i, 1, ev.message)
      break
    }
  }
}

async function runTurn(fn, id, body, tempUser) {
  sending.value = true
  abort = new AbortController()
  let started = false
  try {
    await fn(id, body, ev => {
      if (ev.type === 'start') started = true
      handleEvent(ev, tempUser)
    }, abort.signal)
  } catch (e) {
    // Once the reply has started, the server finishes it regardless of this
    // connection — a dropped stream (throttled background tab, network blip)
    // is recovered by polling in `finally`, so there's nothing to report
    if (e.name !== 'AbortError' && !started) {
      showToast(e.message, 'error')
      // Edit/retry (they name a message_id) swap the branch optimistically — resync with the server
      if (body.message_id != null) loadConversation(id)
      else if (tempUser) messages.value = messages.value.filter(m => m !== tempUser)
    }
  } finally {
    sending.value = false
    streamingId.value = null
    abort = null
    bumpConversation(id)
    ensurePolling()
    refreshBalances()
  }
}

async function send() {
  if (!canSend.value) return
  let id
  try {
    id = await ensureConversation()
  } catch (e) {
    return showToast(e.message, 'error')
  }
  const content = draft.value.trim()
  const files = attachments.value.filter(a => a.file)
  const tempUser = reactive({
    id: `tmp-${Date.now()}`, role: 'user', content, status: 'done',
    media: files.map(a => ({ id: a.key, kind: 'image', status: 'done', file: a.file })),
  })
  messages.value.push(tempUser)
  draft.value = ''
  attachments.value = []
  autosize()
  scrollToBottom(true)
  await runTurn(sendChatMessage, id, { ...turnSettings(), content, attachments: files.map(a => a.file) }, tempUser)
}

// Retry/edit add a new branch beside the message; the old one stays
// reachable with the ‹ 1/2 › arrows. Show the new branch right away.
async function retry(msg) {
  if (sending.value) return
  const i = messages.value.findIndex(m => m.id === msg.id)
  if (i === -1) return
  messages.value = messages.value.slice(0, i)
  // The prompt's mode tag follows the latest run (the server updates it too)
  const prompt = messages.value[i - 1]
  if (prompt?.role === 'user') prompt.mode = mode.value
  await runTurn(retryChatMessage, convId.value, { ...turnSettings(), message_id: msg.id }, null)
}

async function editMessage(msg, content) {
  if (sending.value) return
  const i = messages.value.findIndex(m => m.id === msg.id)
  if (i === -1) return
  const tempUser = reactive({ ...msg, id: `tmp-${Date.now()}`, content, mode: mode.value, siblings: [] })
  messages.value = [...messages.value.slice(0, i), tempUser]
  scrollToBottom(true)
  await runTurn(editChatMessage, convId.value,
    { ...turnSettings(), message_id: msg.id, content }, tempUser)
}

// Same as an edit with unchanged text: a new branch with a fresh reply
async function resendMessage(msg) {
  await editMessage(msg, msg.content || '')
}

function deleteQuestion({ other_versions: versions, other_messages: after }) {
  const plural = (n, word) => `${n} ${word}${n === 1 ? '' : 's'}`
  let extra = ''
  if (versions && after) extra = ` This also removes ${plural(versions, 'other version')} and ${plural(after, 'message')} that followed them.`
  else if (versions) extra = ` This also removes ${plural(versions, 'other version')}.`
  else if (after) extra = ` This also removes ${plural(after, 'message')} on other branches.`
  return `Delete this prompt and its reply?${extra} Images and videos stay in Media.`
}

// Remove a prompt and its reply; the models stop seeing them, media stays in the Library
async function deleteExchange(msg) {
  if (sending.value) return
  try {
    if (!confirm(deleteQuestion(await fetchDeleteInfo(msg.id)))) return
    const data = await deleteChatExchange(msg.id)
    conversation.value = data.conversation
    messages.value = data.messages
  } catch (e) {
    showToast(e.message, 'error')
  }
}

async function switchBranch(messageId) {
  if (sending.value) return
  try {
    const data = await switchChatBranch(convId.value, messageId)
    conversation.value = data.conversation
    messages.value = data.messages
    ensurePolling()
  } catch (e) {
    showToast(e.message, 'error')
  }
}

// Chat creations live in Media, with everything else (filtered to chats)
function openLibrary() {
  sidebarOpen.value = false
  router.push({ name: 'media', query: { origin: 'chat' } })
}

// Retry a failed image/video in place (same or another model). The server
// runs it in the background; polling picks up the result.
async function regenerateMedia(msg, { mediaId, model }) {
  try {
    replaceMessage(await regenerateChatMedia(msg.id, mediaId, model))
    ensurePolling()
  } catch (e) {
    showToast(e.message, 'error')
  }
}

async function pinMedia(msg, { mediaId, pinned: on }) {
  try {
    const { media } = await pinChatMedia(msg.id, mediaId, on)
    // Keep the shown copy's other fields (it may be fresher than `msg`)
    const current = messages.value.find(m => m.id === msg.id)
    if (current) replaceMessage({ ...current, media })
  } catch (e) {
    showToast(e.message, 'error')
  }
}

async function unpinAll() {
  for (const p of pinned.value) await pinMedia(p.msg, { mediaId: p.mediaId, pinned: false })
}

async function stop() {
  if (streamingId.value) {
    try { await cancelChatMessage(streamingId.value) } catch { abort?.abort() }
  }
}

// Swap in a fresher copy of a shown message (matched by id)
function replaceMessage(fresh) {
  const i = messages.value.findIndex(m => m.id === fresh.id)
  if (i !== -1) messages.value.splice(i, 1, fresh)
}

function bumpConversation(id) {
  const i = conversations.value.findIndex(c => c.id === id)
  if (i > 0) conversations.value.unshift(conversations.value.splice(i, 1)[0])
}

function onKeydown(e) {
  if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) {
    e.preventDefault()
    send()
  }
}

function useSuggestion(text, m) {
  draft.value = text
  if (m) mode.value = m
  nextTick(() => { autosize(); textarea.value?.focus() })
}

// ── Polling (anything not covered by a live stream) ─────────────────
// A reply's live SSE stream can drop — a background tab gets throttled or
// frozen, you reload, or you open it mid-reply from elsewhere. The server
// keeps working regardless, so poll such replies until they're done, plus
// any rendering video / retried image.
let pollTimer = null

function hasPending(m) {
  if (m.status === 'streaming') return m.id !== streamingId.value   // no live stream for it
  return !!m.media?.some(x => x.status === 'pending')
}

async function pollOnce() {
  const pending = messages.value.filter(hasPending)
  if (!pending.length) return stopPolling()
  let finished = false
  for (const m of pending) {
    try {
      const fresh = await fetchChatMessage(m.id)
      replaceMessage(fresh)
      finished ||= !hasPending(fresh)
    } catch { /* retry next tick */ }
  }
  if (finished) refreshBalances()   // a video/image landed — it was billed
}

// ── Balances (top of the chat): OpenRouter and Venice dollars, Pollo credits ────
const { creditsRemaining: polloCredits, refreshBalance: refreshPolloBalance } = useSessionCredits()
const openrouterBalance = ref(null)
const veniceBalance = ref(null)

async function refreshBalances() {
  refreshPolloBalance(true)
  if (providers.openrouter) {
    try {
      openrouterBalance.value = (await fetchOpenRouterCredits()).remaining
    } catch { /* shown as — */ }
  }
  if (providers.venice) {
    try {
      veniceBalance.value = (await fetchVeniceBalance()).usd
    } catch { /* shown as — */ }
  }
}

const fmtUsd = (v) => (v == null ? '—' : `$${v.toFixed(2)}`)
const fmtCredits = (v) => (v == null ? '—' : Math.round(v).toLocaleString())

function ensurePolling() {
  if (pollTimer || !messages.value.some(hasPending)) return
  pollTimer = setInterval(pollOnce, 5000)
}

// Coming back to the tab: catch up now rather than on the next tick
function onVisibilityChange() {
  if (document.visibilityState === 'visible' && messages.value.some(hasPending)) {
    pollOnce()
    ensurePolling()
  }
}

function stopPolling() {
  clearInterval(pollTimer)
  pollTimer = null
}

// ── UI helpers ───────────────────────────────────────────────────────
function autosize() {
  nextTick(() => {
    const el = textarea.value
    if (!el) return
    el.style.height = 'auto'
    el.style.height = `${Math.min(el.scrollHeight, 240)}px`
  })
}

// Follow new content unless the user has scrolled up to read. A
// ResizeObserver catches height changes events can't (images loading,
// placeholders swapping for media).
let stickToBottom = true
let resizeObs = null

function onScroll() {
  const el = scroller.value
  if (el) stickToBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 80
}

function scrollToBottom(force = false) {
  if (force) stickToBottom = true
  // Editing an earlier prompt grows the list — don't yank it out of view
  else if (document.activeElement?.closest?.('.edit-box')) return
  nextTick(() => {
    const el = scroller.value
    if (el && stickToBottom) el.scrollTop = el.scrollHeight
  })
}

watch(messagesEl, (el, old) => {
  if (old) resizeObs?.unobserve(old)
  if (el) {
    resizeObs ??= new ResizeObserver(() => scrollToBottom())
    resizeObs.observe(el)
  }
})

function openMedia(m) {
  lightbox.value = m
}

function onGlobalKey(e) {
  if (e.key === 'Escape') lightbox.value = null
}

onMounted(async () => {
  window.addEventListener('keydown', onGlobalKey)
  document.addEventListener('visibilitychange', onVisibilityChange)
  try {
    const status = await fetchChatStatus()
    configured.value = status.configured
    providers.openrouter = status.openrouter ?? status.configured
    providers.venice = !!status.venice
  } catch { /* 401 handled by auth prompt */ }
  loadConversations()
  loadInstructions()
  loadConversation(convId.value)
  if (configured.value) loadModels()
  else modelsLoading.value = false
  refreshBalances()
  textarea.value?.focus()
})

onBeforeUnmount(() => {
  window.removeEventListener('keydown', onGlobalKey)
  document.removeEventListener('visibilitychange', onVisibilityChange)
  abort?.abort()
  stopPolling()
  resizeObs?.disconnect()
})
</script>

<template>
  <div class="chat-layout" :class="{ 'sidebar-open': sidebarOpen }">
    <!-- ── Sidebar: every control lives here ────────────── -->
    <aside class="chat-sidebar">
      <div class="side-top">
        <RouterLink to="/" class="home-link" title="Back to Pollo">← Pollo</RouterLink>
        <button class="new-chat" title="New chat" @click="newChat">＋ New chat</button>
      </div>

      <div class="side-controls">
        <div class="side-section">
          <div class="side-heading">
            <span>Models</span>
            <button class="mini-btn" title="Refresh model lists" :disabled="modelsLoading" @click="loadModels(true)">⟳</button>
          </div>
          <ModelPicker v-model="selected.text" :models="models.text" label="Chat" icon="💬" kind="text" :loading="modelsLoading" />
          <ModelPicker v-model="selected.image" :models="models.image" label="Image" icon="🖼" kind="image" :loading="modelsLoading" />
          <ModelPicker v-model="selected.video" :models="models.video" label="Video" icon="🎬" kind="video" :loading="modelsLoading" />
        </div>

        <div class="side-section">
          <div class="side-heading"><span>Mode</span></div>
          <div class="modes">
            <button
              v-for="m in MODES"
              :key="m.id"
              class="mode"
              :class="{ active: mode === m.id }"
              :title="m.hint"
              @click="mode = m.id"
            >{{ m.icon }} {{ m.label }}</button>
          </div>
          <p class="mode-hint">{{ MODES.find(m => m.id === mode)?.hint }}</p>
        </div>

        <div class="side-section">
          <div class="side-heading">
            <span>Instructions</span>
            <button class="mini-btn" title="Create and edit saved instructions" @click="instructionsOpen = true">Manage</button>
          </div>
          <select
            class="instruction-select"
            :value="instructionId ?? ''"
            aria-label="Custom instructions for this chat"
            @change="setInstruction($event.target.value === '' ? null : Number($event.target.value))"
          >
            <option value="">None</option>
            <option v-for="i in instructions" :key="i.id" :value="i.id">{{ i.name }}{{ i.is_default ? ' (default)' : '' }}</option>
          </select>
          <p v-if="attachedInstruction && (mode === 'video' || (mode === 'image' && !imageInfo?.conversational))" class="mode-hint">
            {{ mode === 'video' ? 'Video models' : 'This image model' }} can't take instructions; they apply in Auto and Chat modes.
          </p>
        </div>

        <div class="side-section">
          <div class="side-heading">
            <span>Characters</span>
            <button class="mini-btn" title="All characters" @click="router.push({ name: 'characters' })">Manage</button>
          </div>
          <template v-if="!characterSupport.ok">
            <p class="side-warn">{{ characterSupport.reason }}</p>
            <p v-if="attachedCharacters.length" class="mode-hint">
              {{ attachedCharacters.map(c => c.name).join(', ') }} {{ attachedCharacters.length === 1 ? 'stays' : 'stay' }}
              attached and will be used again when you switch back.
            </p>
          </template>
          <CharacterPicker
            v-else
            :model-value="characterIds"
            :characters="characters"
            create-label="＋ New character (this chat)"
            @update:model-value="setCharacters"
            @edit="editCharacter"
            @create="newCharacter()"
          />
          <p v-if="characterSupport.ok && attachedCharacters.length" class="mode-hint">
            {{ mode === 'auto' ? 'The chat model knows them and sends their description and images when it puts one in a picture.'
              : mode === 'image' ? 'Their descriptions and images go with every image.'
              : 'The chat model knows them.' }}
          </p>
        </div>

        <div v-if="mode === 'auto' || mode === 'text'" class="side-section">
          <div class="side-heading">
            <span>Memory</span>
            <span class="heading-value">{{ historyLimit ? `${historyLimit} messages` : 'All' }}</span>
          </div>
          <input
            v-model.number="memoryIndex"
            class="memory-slider"
            type="range"
            min="0"
            :max="MEMORY_STEPS.length - 1"
            step="1"
            aria-label="Messages of history sent to the chat model"
          />
          <p class="mode-hint">{{ memoryHint }} More memory means better continuity but more tokens per reply.</p>
        </div>

        <div v-if="mode !== 'video'" class="side-section">
          <div class="side-heading">
            <span>Chat images</span>
            <span class="heading-value">{{ imageLimit === null ? 'All' : imageLimit }}</span>
          </div>
          <input
            v-model.number="imageIndex"
            class="memory-slider"
            type="range"
            min="0"
            :max="IMAGE_STEPS.length - 1"
            step="1"
            aria-label="Recent chat images sent with each request"
          />
          <p class="mode-hint">
            Recent chat images the models see, and the most sent as references with a new picture.
            Character images always go on top. More helps consistency but makes bigger, pricier requests.
          </p>
        </div>

        <div v-if="showImageOpts" class="side-section">
          <div class="side-heading"><span>Image options</span></div>
          <div class="opts">
            <select v-model="imageOpts.aspect_ratio" title="Aspect ratio">
              <option value="">Ratio: auto</option>
              <option v-for="r in imageRatioOptions" :key="r" :value="r">{{ r }}</option>
            </select>
            <select v-if="imageResOptions.length" v-model="imageOpts.resolution" title="Resolution">
              <option value="">Res: default</option>
              <option v-for="r in imageResOptions" :key="r" :value="r">{{ r }}</option>
            </select>
          </div>
        </div>

        <div v-if="showVideoOpts" class="side-section">
          <div class="side-heading"><span>Video options</span></div>
          <div class="opts">
            <select v-model="videoOpts.aspect_ratio" title="Aspect ratio (ignored when animating an image — the image sets it)">
              <option value="">Ratio: auto</option>
              <option v-for="r in videoRatioOptions" :key="r" :value="r">{{ r }}</option>
            </select>
            <select v-if="videoResOptions.length" v-model="videoOpts.resolution" title="Resolution (Kling: quality tier)">
              <option value="">Res: default</option>
              <option v-for="r in videoResOptions" :key="r" :value="r">{{ r }}</option>
            </select>
            <select v-if="durationOptions.length" v-model="videoOpts.duration" title="Duration">
              <option value="">Length: {{ mode === 'auto' ? 'auto' : 'default' }}</option>
              <option v-for="d in durationOptions" :key="d" :value="d">{{ d }}s</option>
            </select>
            <label v-if="videoInfo?.generate_audio" class="opt-check">
              <input type="checkbox" v-model="videoOpts.generate_audio" /> Audio
            </label>
          </div>
        </div>
        <p v-if="mode === 'auto' && (showImageOpts || showVideoOpts)" class="mode-hint">
          In Auto mode these apply whenever the chat model makes an image or video. "auto" lets it choose.
        </p>

        <p v-if="modeWarning" class="side-warn">{{ modeWarning }}</p>
        <p v-if="!configured" class="side-warn">
          No chat provider is configured. Add <code>OPENROUTER_API_KEY</code> and/or <code>VENICE_API_KEY</code> to the server's <code>.env</code> and restart.
        </p>
      </div>

      <button class="library-link" title="Every image and video from your chats, in Media" @click="openLibrary">🗂 Media</button>

      <div class="side-heading chats-heading"><span>Chats</span></div>
      <div class="conv-list">
        <div
          v-for="c in conversations"
          :key="c.id"
          class="conv-item"
          :class="{ active: c.id === convId }"
          @click="openConversation(c.id)"
        >
          <span class="conv-title">{{ c.title }}</span>
          <span class="conv-actions" @click.stop>
            <button title="Rename" @click="rename(c)">✎</button>
            <button title="Delete" @click="removeConversation(c)">🗑</button>
          </span>
        </div>
        <p v-if="!conversations.length" class="conv-empty">No chats yet</p>
      </div>

      <div class="side-bottom">
        <button
          class="mini-btn key"
          :class="{ missing: !hasKey }"
          :title="hasKey ? 'API key set — click to change' : 'No API key — click to set'"
          @click="showKeyModal = true"
        >🔑 {{ hasKey ? 'Signed in' : 'Sign in' }}</button>
      </div>
    </aside>
    <div class="sidebar-scrim" @click="sidebarOpen = false"></div>

    <!-- ── Main: conversation fills the height ──────────── -->
    <section
      class="chat-main"
      @dragover.prevent="dragging = true"
      @dragleave.self="dragging = false"
      @drop.prevent="onDrop"
    >
      <button class="sidebar-toggle" title="Chats & settings" @click="sidebarOpen = !sidebarOpen">☰</button>

      <div class="balances">
        <span v-if="providers.openrouter" class="balance" title="OpenRouter balance — credits bought minus used (chat text, OpenRouter images/videos)">
          OpenRouter <b>{{ fmtUsd(openrouterBalance) }}</b>
        </span>
        <span v-if="providers.venice" class="balance venice" title="Venice balance in USD (Venice text, images and videos)">
          Venice <b>{{ fmtUsd(veniceBalance) }}</b>
        </span>
        <RouterLink to="/usage" class="balance pollo" title="Pollo credits remaining (Pollo images/videos) — open Usage">
          Pollo <b>{{ fmtCredits(polloCredits) }}</b>
        </RouterLink>
      </div>

      <div ref="scroller" class="chat-scroll" @scroll.passive="onScroll">
        <div v-if="loadingConv" class="center-note"><div class="spinner"></div></div>

        <div v-else-if="!messages.length" class="welcome">
          <h2><span>Hello.</span> What shall we make?</h2>
          <p>Chat with any OpenRouter model. Ask for a picture or a clip and it'll make one with your image and video models.</p>
          <div class="suggestions">
            <button @click="useSuggestion('Explain how diffusion models generate images, simply.', 'auto')">💡 Explain diffusion models</button>
            <button @click="useSuggestion('Draw a cozy isometric cabin in a snowy forest at dusk, warm window light', 'auto')">🖼 Draw a snowy cabin</button>
            <button @click="useSuggestion('Make a short video of ocean waves crashing on black sand at golden hour, slow dolly shot', 'auto')">🎬 Video of waves</button>
            <button @click="useSuggestion('Brainstorm 5 visual concepts for a coffee brand launch, then draw your favourite', 'auto')">✨ Brainstorm & draw</button>
          </div>
        </div>

        <div v-else ref="messagesEl" class="messages">
          <ChatMessage
            v-for="m in messages"
            :key="m.id"
            :message="m"
            :conv-id="convId || ''"
            :can-retry="m.id === lastAssistantId && !sending"
            :can-edit="m.role === 'user' && typeof m.id === 'number' && !sending"
            :can-switch="!sending"
            @retry="retry(m)"
            @edit="content => editMessage(m, content)"
            @resend="resendMessage(m)"
            @branch="switchBranch"
            @use-image="useImage"
            @use-text="useText"
            @regenerate="payload => regenerateMedia(m, payload)"
            @pin="payload => pinMedia(m, payload)"
            @delete="deleteExchange(m)"
            @stop="stop"
            @open-media="openMedia"
          />
        </div>
      </div>

      <!-- ── Composer: one row ──────────────────────────── -->
      <div class="composer-wrap">
        <div class="composer" :class="{ dragging }">
          <div v-if="attachments.length" class="att-row">
            <div v-for="a in attachments" :key="a.key" class="att">
              <img :src="a.preview" alt="" />
              <div v-if="a.uploading" class="att-busy"><div class="spinner"></div></div>
              <button class="att-x" @click="removeAttachment(a)" title="Remove">✕</button>
            </div>
          </div>

          <div v-if="characterSupport.ok && attachedCharacters.length" class="pinned-row">
            <span>👤 {{ attachedCharacters.map(c => c.name).join(', ') }}</span>
            <button @click="sidebarOpen = true">Change</button>
          </div>

          <div v-if="pinned.length && mode !== 'text'" class="pinned-row">
            <span>📌 {{ pinned.length }} image{{ pinned.length !== 1 ? 's' : '' }} pinned: sent as references with every new image</span>
            <button @click="unpinAll">Unpin all</button>
          </div>

          <div class="composer-row">
            <label class="icon-btn" title="Attach images (or paste / drop)">
              📎
              <input type="file" accept="image/png,image/jpeg,image/webp,image/gif" multiple hidden @change="addFiles($event.target.files); $event.target.value = ''" />
            </label>
            <button class="icon-btn" title="Attach from your uploads and creations" @click="libraryOpen = true">🗂</button>
            <button class="mode-chip" :title="`Mode: ${currentMode.label} — click to switch`" @click="cycleMode">
              {{ currentMode.icon }} {{ currentMode.label }}
            </button>
            <textarea
              ref="textarea"
              v-model="draft"
              rows="1"
              :placeholder="mode === 'image' ? 'Describe an image…' : mode === 'video' ? 'Describe a video (attach an image to animate it)…' : 'Message, or ask for an image or video…'"
              @input="autosize"
              @keydown="onKeydown"
              @paste="onPaste"
            ></textarea>
            <button v-if="sending" class="send stop" title="Stop" @click="stop">■</button>
            <button v-else class="send" :disabled="!canSend" title="Send (Enter)" @click="send">↑</button>
          </div>
        </div>
      </div>
    </section>

    <MediaPicker
      :open="libraryOpen"
      title="Attach images"
      :max="Math.max(1, 8 - attachments.length)"
      @pick="attachFromLibrary"
      @close="libraryOpen = false"
    />

    <CharacterEditor
      :open="charEditor.open"
      :character="charEditor.character"
      :conversation-id="charEditor.conversationId"
      :seed="charEditor.seed"
      @close="charEditor.open = false"
      @saved="onCharacterSaved"
      @deleted="onCharacterDeleted"
    />

    <InstructionsDialog
      :open="instructionsOpen"
      :instructions="instructions"
      :select-id="instructionId"
      @close="instructionsOpen = false"
      @changed="onInstructionsChanged"
    />

    <!-- ── Lightbox ─────────────────────────────────────── -->
    <Teleport to="body">
      <div v-if="lightbox" class="lightbox" @click="lightbox = null">
        <img :src="lightbox.url" alt="" @click.stop />
        <p v-if="lightbox.prompt" class="lightbox-caption" @click.stop>{{ lightbox.prompt }}</p>
        <div v-if="lightbox.file" class="lightbox-actions" @click.stop>
          <button class="lightbox-animate" @click="useImage({ file: lightbox.file, mode: 'image' })">🖼 Make a picture from this</button>
          <button class="lightbox-animate" @click="useImage({ file: lightbox.file, mode: 'video' })">🎬 Make a video from this</button>
          <button class="lightbox-animate" @click="characterFromImage(lightbox.file)">👤 Make a character from this</button>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<style scoped>
.pinned-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 6px 12px 0;
  font-size: 0.75rem;
  color: var(--text2);
}

.pinned-row button {
  border: none;
  background: none;
  color: var(--accent);
  font-size: 0.75rem;
  cursor: pointer;
  padding: 0;
}

.chat-layout {
  display: flex;
  height: 100vh;
  height: 100dvh;
  position: relative;
  overflow: hidden;   /* only the panes inside scroll, never the page */
  background: var(--bg);
}

/* Slim scrollbars that only show while hovering the pane */
.side-controls,
.conv-list,
.chat-scroll {
  scrollbar-width: thin;
  scrollbar-color: transparent transparent;
}

.side-controls:hover,
.conv-list:hover,
.chat-scroll:hover {
  scrollbar-color: #3a3a3a transparent;
}

.side-controls::-webkit-scrollbar,
.conv-list::-webkit-scrollbar,
.chat-scroll::-webkit-scrollbar {
  width: 6px;
}

.side-controls::-webkit-scrollbar-thumb,
.conv-list::-webkit-scrollbar-thumb,
.chat-scroll::-webkit-scrollbar-thumb {
  background: transparent;
  border-radius: 3px;
}

.side-controls:hover::-webkit-scrollbar-thumb,
.conv-list:hover::-webkit-scrollbar-thumb,
.chat-scroll:hover::-webkit-scrollbar-thumb {
  background: #3a3a3a;
}

/* ── Sidebar ─────────────────────────── */
.chat-sidebar {
  width: 280px;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  background: #141414;
  border-right: 1px solid #222;
  min-height: 0;
}

.side-top {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px 12px 4px;
}

.home-link {
  color: var(--text2);
  text-decoration: none;
  font-size: 0.82rem;
  padding: 6px 8px;
  border-radius: 8px;
  white-space: nowrap;
}

.home-link:hover {
  color: var(--text);
  background: var(--surface2);
}

.new-chat {
  flex: 1;
  padding: 8px 10px;
  border-radius: 10px;
  border: 1px solid var(--border);
  background: var(--surface2);
  color: var(--text);
  cursor: pointer;
  font-weight: 600;
  font-size: 0.85rem;
  transition: border-color 0.2s;
}

.new-chat:hover {
  border-color: var(--accent);
}

.side-controls {
  padding: 4px 12px 0;
  display: flex;
  flex-direction: column;
  gap: 14px;
  /* When the window is short the settings scroll, leaving room for the chats */
  flex: 0 1 auto;
  min-height: 0;
  overflow-y: auto;
  overflow-x: hidden;
}

.side-section {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.side-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 0.68rem;
  text-transform: uppercase;
  letter-spacing: 0.6px;
  color: var(--text2);
  padding: 8px 2px 0;
}

.library-link {
  margin: 14px 12px 0;
  padding: 8px 10px;
  border-radius: 10px;
  border: 1px solid transparent;
  background: none;
  color: var(--text2);
  text-align: left;
  font-size: 0.87rem;
  cursor: pointer;
}

.library-link:hover {
  background: var(--surface2);
  color: var(--text);
}

.chats-heading {
  padding: 16px 14px 4px;
}

.mini-btn {
  background: none;
  border: none;
  color: var(--text2);
  cursor: pointer;
  border-radius: 6px;
  padding: 2px 6px;
  font-size: 0.85rem;
}

.mini-btn:hover:not(:disabled) {
  background: var(--surface2);
  color: var(--text);
}

.modes {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 4px;
}

.mode {
  padding: 6px 8px;
  border-radius: 8px;
  border: 1px solid var(--border);
  background: transparent;
  color: var(--text2);
  font-size: 0.8rem;
  cursor: pointer;
  transition: all 0.15s;
}

.mode:hover {
  color: var(--text);
}

.mode.active {
  background: rgba(108, 92, 231, 0.2);
  border-color: var(--accent);
  color: var(--text);
}

.instruction-select {
  width: 100%;
  padding: 6px 8px;
  font-size: 0.82rem;
  border-radius: 8px;
}

.heading-value {
  text-transform: none;
  letter-spacing: 0;
  color: var(--text);
  font-size: 0.75rem;
}

.memory-slider {
  width: 100%;
  padding: 0;
  border: none;
  background: transparent;
  accent-color: var(--accent);
  cursor: pointer;
}

.mode-hint {
  font-size: 0.72rem;
  color: var(--text2);
  line-height: 1.4;
}

.opts {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 6px;
  align-items: center;
}

.opts select {
  padding: 5px 8px;
  font-size: 0.78rem;
  border-radius: 8px;
  min-width: 0;
}

.opt-check {
  display: flex;
  align-items: center;
  gap: 5px;
  font-size: 0.78rem;
  text-transform: none;
  letter-spacing: 0;
  color: var(--text);
  cursor: pointer;
}

.side-warn {
  font-size: 0.75rem;
  line-height: 1.4;
  color: var(--yellow);
  background: rgba(253, 203, 110, 0.07);
  border: 1px solid rgba(253, 203, 110, 0.25);
  border-radius: 8px;
  padding: 8px 10px;
}

.side-warn code {
  font-size: 0.7rem;
}

.conv-list {
  flex: 1 0 140px;
  min-height: 140px;
  overflow-y: auto;
  padding: 0 8px 8px;
}

.conv-item {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 7px 10px;
  border-radius: 8px;
  cursor: pointer;
  font-size: 0.85rem;
  color: var(--text2);
}

.conv-item:hover {
  background: var(--surface2);
  color: var(--text);
}

.conv-item.active {
  background: rgba(108, 92, 231, 0.18);
  color: var(--text);
}

.conv-title {
  flex: 1;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.conv-actions {
  display: none;
  gap: 2px;
}

.conv-item:hover .conv-actions {
  display: flex;
}

.conv-actions button {
  background: none;
  border: none;
  cursor: pointer;
  font-size: 0.8rem;
  padding: 2px 4px;
  border-radius: 4px;
  color: var(--text2);
}

.conv-actions button:hover {
  background: var(--border);
}

.conv-empty {
  padding: 12px;
  font-size: 0.8rem;
  color: var(--text2);
  text-align: center;
}

.side-bottom {
  padding: 8px 12px 12px;
  border-top: 1px solid #222;
}

.mini-btn.key {
  font-size: 0.78rem;
}

.mini-btn.key.missing {
  color: var(--red);
}

.sidebar-scrim,
.sidebar-toggle {
  display: none;
}

/* ── Main ────────────────────────────── */
.chat-main {
  flex: 1;
  min-width: 0;
  min-height: 0;
  display: flex;
  flex-direction: column;
  position: relative;
}

.balances {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  padding: 8px 16px 0;
}

.balance {
  font-size: 0.75rem;
  color: var(--text2);
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 999px;
  padding: 3px 10px;
  white-space: nowrap;
  text-decoration: none;
}

.balance b {
  color: var(--text);
  font-family: 'SF Mono', 'Fira Code', monospace;
  font-weight: 600;
}

.balance.venice b {
  color: #e8a33d;
}

.balance.pollo b {
  color: var(--accent2);
}

.balance.pollo:hover {
  border-color: var(--accent2);
}

.chat-scroll {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 28px 24px 12px;
}

.messages {
  display: flex;
  flex-direction: column;
  gap: 22px;
}

.center-note {
  display: grid;
  place-items: center;
  height: 100%;
}

/* ── Welcome ─────────────────────────── */
.welcome {
  max-width: 720px;
  margin: 14vh auto 0;
}

.welcome h2 {
  font-size: 2rem;
  font-weight: 600;
  line-height: 1.25;
  margin-bottom: 10px;
}

.welcome h2 span {
  background: linear-gradient(90deg, var(--accent2), #4b8bf5, #e17055);
  -webkit-background-clip: text;
  background-clip: text;
  color: transparent;
}

.welcome p {
  color: var(--text2);
  margin-bottom: 24px;
}

.suggestions {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 10px;
}

.suggestions button {
  text-align: left;
  padding: 14px;
  border-radius: 12px;
  border: 1px solid var(--border);
  background: var(--surface2);
  color: var(--text);
  cursor: pointer;
  font-size: 0.87rem;
  line-height: 1.4;
  transition: border-color 0.2s, transform 0.2s;
}

.suggestions button:hover {
  border-color: var(--accent);
  transform: translateY(-1px);
}

/* ── Composer ────────────────────────── */
.composer-wrap {
  padding: 0 24px 14px;
}

.composer {
  max-width: 820px;
  margin: 0 auto;
  background: var(--surface2);
  border: 1px solid var(--border);
  border-radius: 24px;
  padding: 6px 6px 6px 8px;
  transition: border-color 0.2s, box-shadow 0.2s;
}

.composer:focus-within {
  border-color: rgba(108, 92, 231, 0.6);
}

.composer.dragging {
  border-color: var(--accent);
  box-shadow: 0 0 0 3px rgba(108, 92, 231, 0.25);
}

.composer-row {
  display: flex;
  align-items: flex-end;
  gap: 6px;
}

.composer textarea {
  flex: 1;
  min-width: 0;
  min-height: 24px;
  max-height: 240px;
  resize: none;
  border: none;
  background: transparent;
  padding: 7px 4px;
  font-size: 0.95rem;
  line-height: 1.5;
  overflow-y: auto;
}

.icon-btn {
  width: 36px;
  height: 36px;
  flex-shrink: 0;
  display: grid;
  place-items: center;
  border-radius: 50%;
  color: var(--text2);
  cursor: pointer;
  font-size: 1.05rem;
}

button.icon-btn {
  border: none;
  background: none;
}

.icon-btn:hover {
  background: var(--surface);
  color: var(--text);
}

.mode-chip {
  flex-shrink: 0;
  height: 30px;
  margin-bottom: 3px;
  padding: 0 10px;
  border-radius: 999px;
  border: 1px solid var(--accent);
  background: rgba(108, 92, 231, 0.15);
  color: var(--text);
  font-size: 0.75rem;
  cursor: pointer;
  white-space: nowrap;
}

.att-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  padding: 6px 4px 8px;
}

.att {
  position: relative;
  width: 64px;
  height: 64px;
}

.att img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  border-radius: 10px;
  border: 1px solid var(--border);
}

.att-busy {
  position: absolute;
  inset: 0;
  display: grid;
  place-items: center;
  background: rgba(0, 0, 0, 0.5);
  border-radius: 10px;
}

.att-x {
  position: absolute;
  top: -6px;
  right: -6px;
  width: 20px;
  height: 20px;
  border-radius: 50%;
  border: 1px solid var(--border);
  background: var(--surface);
  color: var(--text);
  font-size: 0.65rem;
  cursor: pointer;
}

.send {
  width: 36px;
  height: 36px;
  flex-shrink: 0;
  border-radius: 50%;
  border: none;
  background: linear-gradient(145deg, var(--accent), #5a4bd1);
  color: white;
  font-size: 1.1rem;
  font-weight: 700;
  cursor: pointer;
  transition: opacity 0.2s, transform 0.15s;
}

.send:hover:not(:disabled) {
  transform: scale(1.06);
}

.send:disabled {
  opacity: 0.35;
  cursor: not-allowed;
}

.send.stop {
  background: var(--text);
  color: var(--bg);
  font-size: 0.8rem;
}

/* ── Lightbox ────────────────────────── */
.lightbox {
  position: fixed;
  inset: 0;
  z-index: 1000;
  background: rgba(0, 0, 0, 0.9);
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding: 24px;
  cursor: zoom-out;
}

.lightbox img {
  max-width: 100%;
  max-height: calc(100vh - 120px);
  object-fit: contain;
  border-radius: 8px;
  cursor: default;
}

.lightbox-actions {
  display: flex;
  gap: 8px;
}

.lightbox-animate {
  padding: 8px 16px;
  border: none;
  border-radius: 999px;
  background: linear-gradient(145deg, var(--accent), #5a4bd1);
  color: white;
  font-size: 0.85rem;
  font-weight: 600;
  cursor: pointer;
}

.lightbox-caption {
  max-width: 720px;
  color: var(--text2);
  font-size: 0.85rem;
  text-align: center;
  cursor: text;
}

/* ── Narrow screens: sidebar becomes a drawer ── */
@media (max-width: 860px) {
  .chat-sidebar {
    position: absolute;
    inset: 0 auto 0 0;
    z-index: 20;
    width: min(300px, 86vw);
    transform: translateX(-100%);
    transition: transform 0.2s ease;
  }

  .sidebar-open .chat-sidebar {
    transform: none;
  }

  .sidebar-open .sidebar-scrim {
    display: block;
    position: absolute;
    inset: 0;
    z-index: 10;
    background: rgba(0, 0, 0, 0.5);
  }

  .sidebar-toggle {
    display: grid;
    place-items: center;
    position: absolute;
    top: 10px;
    left: 10px;
    z-index: 5;
    width: 36px;
    height: 36px;
    border-radius: 10px;
    border: 1px solid var(--border);
    background: rgba(20, 20, 20, 0.85);
    color: var(--text);
    cursor: pointer;
    font-size: 1.05rem;
  }

  .chat-scroll {
    padding: 56px 12px 8px;
  }

  .composer-wrap {
    padding: 0 8px 8px;
  }

  .welcome {
    margin-top: 4vh;
  }

  .welcome h2 {
    font-size: 1.5rem;
  }
}
</style>

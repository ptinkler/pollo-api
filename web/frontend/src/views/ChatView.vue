<script setup>
import { ref, reactive, computed, watch, nextTick, onMounted, onBeforeUnmount, inject, provide } from 'vue'
import { useRoute, useRouter, RouterLink } from 'vue-router'
import { useAuth } from '../composables/useAuth'
import ModelPicker from '../components/chat/ModelPicker.vue'
import ChatMessage from '../components/chat/ChatMessage.vue'
import ChatLibrary from '../components/chat/ChatLibrary.vue'
import {
  fetchChatStatus, fetchChatModels, fetchConversations, fetchConversation,
  createConversation, deleteConversation, renameConversation, fetchChatMessage,
  cancelChatMessage, uploadChatAttachment, chatMediaUrl, sendChatMessage, retryChatMessage,
  editChatMessage, regenerateChatMedia,
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
const MAX_CONTEXT_IMAGES = 4   // mirrors MAX_HISTORY_IMAGES in web/chat.py

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
const options = reactive({ aspect_ratio: '', resolution: '', duration: '', generate_audio: true })

watch([() => ({ ...selected }), mode, memoryIndex], () => {
  try {
    localStorage.setItem(STORE_KEY, JSON.stringify({ ...selected, mode: mode.value, memory: historyLimit.value }))
  } catch { /* storage unavailable */ }
}, { deep: true })

// ── Server state ─────────────────────────────────────────────────────
const configured = ref(true)
const models = reactive({ text: [], image: [], video: [] })
provide('chatModels', models)   // for "Try another model" on failed media
const modelsLoading = ref(true)
const conversations = ref([])
const conversation = ref(null)
const messages = ref([])
const loadingConv = ref(false)

const convId = computed(() => route.params.id || null)
const isLibrary = computed(() => route.name === 'chat-library')

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
  const imgs = `the ${MAX_CONTEXT_IMAGES} most recent images`
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

const ratioOptions = computed(() => {
  const info = mode.value === 'video' ? videoInfo.value : imageInfo.value
  return info?.aspect_ratios?.length ? info.aspect_ratios : DEFAULT_RATIOS
})
const resolutionOptions = computed(() => {
  const info = mode.value === 'video' ? videoInfo.value : imageInfo.value
  return info?.resolutions || []
})
const durationOptions = computed(() => videoInfo.value?.durations || [])

const modeWarning = computed(() => {
  if (mode.value === 'image' && !selected.image) return 'Pick an image model to use Image mode.'
  if (mode.value === 'video' && !selected.video) return 'Pick a video model to use Video mode.'
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

async function loadConversations() {
  try {
    conversations.value = (await fetchConversations()).conversations
  } catch { /* shown elsewhere via 401 prompt */ }
}

async function loadConversation(id) {
  stopPolling()
  if (!id) {
    conversation.value = null
    messages.value = []
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
  })
  conversation.value = conv
  conversations.value = [conv, ...conversations.value]
  skipLoadFor = conv.id
  await router.replace({ name: 'chat-conversation', params: { id: conv.id } })
  return conv.id
}

function newChat() {
  sidebarOpen.value = false
  if (convId.value) router.push({ name: 'chat' })
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
    const updated = await renameConversation(c.id, title)
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
function turnSettings() {
  const body = {
    mode: mode.value,
    history_limit: historyLimit.value,
    text_model: selected.text || null,
    image_model: selected.image || null,
    video_model: selected.video || null,
  }
  if (mode.value === 'image' || mode.value === 'video') {
    body.options = {
      aspect_ratio: options.aspect_ratio || null,
      resolution: options.resolution || null,
      duration: mode.value === 'video' && options.duration ? Number(options.duration) : null,
      generate_audio: mode.value === 'video' && videoInfo.value?.generate_audio ? options.generate_audio : null,
    }
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
  try {
    await fn(id, body, ev => handleEvent(ev, tempUser), abort.signal)
  } catch (e) {
    if (e.name !== 'AbortError') {
      showToast(e.message, 'error')
      if (tempUser) messages.value = messages.value.filter(m => m !== tempUser)
      // Edit/retry trim history optimistically — resync with the server
      else loadConversation(id)
    }
  } finally {
    sending.value = false
    streamingId.value = null
    abort = null
    bumpConversation(id)
    ensurePolling()
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

async function retry(msg) {
  if (sending.value) return
  messages.value = messages.value.filter(m => m.id !== msg.id)
  await runTurn(retryChatMessage, convId.value, { ...turnSettings(), message_id: msg.id }, null)
}

async function editMessage(msg, content) {
  if (sending.value) return
  const i = messages.value.findIndex(m => m.id === msg.id)
  if (i === -1) return
  // Mirror the server: this prompt stays (with new text), everything after goes
  messages.value = messages.value.slice(0, i + 1)
  messages.value[i] = { ...msg, content }
  scrollToBottom(true)
  await runTurn(editChatMessage, convId.value, { ...turnSettings(), message_id: msg.id, content }, null)
}

// Same as an edit with unchanged text: drop everything after the prompt
// (media goes to the Library) and generate a fresh reply
async function resendMessage(msg) {
  const later = laterCount(msg)
  if (later > 1 && !confirm(`Retry this prompt? The ${later} messages after it will be replaced. Generated images/videos stay in the Library.`)) return
  await editMessage(msg, msg.content || '')
}

function laterCount(m) {
  const i = messages.value.findIndex(x => x.id === m.id)
  return i === -1 ? 0 : messages.value.length - i - 1
}

function openLibrary() {
  sidebarOpen.value = false
  router.push({ name: 'chat-library' })
}

// Retry a failed image/video in place (same or another model). The server
// runs it in the background; polling picks up the result.
async function regenerateMedia(msg, { mediaId, model }) {
  try {
    const fresh = await regenerateChatMedia(msg.id, mediaId, model)
    const i = messages.value.findIndex(m => m.id === msg.id)
    if (i !== -1) messages.value.splice(i, 1, fresh)
    ensurePolling()
  } catch (e) {
    showToast(e.message, 'error')
  }
}

async function stop() {
  if (streamingId.value) {
    try { await cancelChatMessage(streamingId.value) } catch { abort?.abort() }
  }
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

// ── Video polling ────────────────────────────────────────────────────
let pollTimer = null

function hasPending(m) {
  return m.status !== 'streaming' && m.media?.some(x => x.status === 'pending')
}

function ensurePolling() {
  if (pollTimer || !messages.value.some(hasPending)) return
  pollTimer = setInterval(async () => {
    const pending = messages.value.filter(hasPending)
    if (!pending.length) return stopPolling()
    for (const m of pending) {
      try {
        const fresh = await fetchChatMessage(m.id)
        const i = messages.value.findIndex(x => x.id === m.id)
        if (i !== -1) messages.value.splice(i, 1, fresh)
      } catch { /* retry next tick */ }
    }
  }, 5000)
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
  try {
    configured.value = (await fetchChatStatus()).configured
  } catch { /* 401 handled by auth prompt */ }
  loadConversations()
  loadConversation(convId.value)
  if (configured.value) loadModels()
  else modelsLoading.value = false
  textarea.value?.focus()
})

onBeforeUnmount(() => {
  window.removeEventListener('keydown', onGlobalKey)
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

        <div v-if="mode === 'image' || mode === 'video'" class="side-section">
          <div class="side-heading"><span>{{ mode === 'video' ? 'Video' : 'Image' }} options</span></div>
          <div class="opts">
            <select v-model="options.aspect_ratio" title="Aspect ratio">
              <option value="">Ratio: auto</option>
              <option v-for="r in ratioOptions" :key="r" :value="r">{{ r }}</option>
            </select>
            <select v-if="resolutionOptions.length" v-model="options.resolution" title="Resolution">
              <option value="">Res: default</option>
              <option v-for="r in resolutionOptions" :key="r" :value="r">{{ r }}</option>
            </select>
            <select v-if="mode === 'video' && durationOptions.length" v-model="options.duration" title="Duration">
              <option value="">Length: default</option>
              <option v-for="d in durationOptions" :key="d" :value="d">{{ d }}s</option>
            </select>
            <label v-if="mode === 'video' && videoInfo?.generate_audio" class="opt-check">
              <input type="checkbox" v-model="options.generate_audio" /> Audio
            </label>
          </div>
        </div>

        <p v-if="modeWarning" class="side-warn">{{ modeWarning }}</p>
        <p v-if="!configured" class="side-warn">
          OpenRouter isn't configured. Add <code>OPENROUTER_API_KEY</code> to the server's <code>.env</code> and restart.
        </p>
      </div>

      <button class="library-link" :class="{ active: isLibrary }" @click="openLibrary">🖼 Library</button>

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

      <div ref="scroller" class="chat-scroll" @scroll.passive="onScroll">
        <ChatLibrary v-if="isLibrary" @open-media="openMedia" />

        <div v-else-if="loadingConv" class="center-note"><div class="spinner"></div></div>

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
            :later-count="m.role === 'user' ? laterCount(m) : 0"
            @retry="retry(m)"
            @edit="content => editMessage(m, content)"
            @resend="resendMessage(m)"
            @regenerate="payload => regenerateMedia(m, payload)"
            @stop="stop"
            @open-media="openMedia"
          />
        </div>
      </div>

      <!-- ── Composer: one row ──────────────────────────── -->
      <div v-if="!isLibrary" class="composer-wrap">
        <div class="composer" :class="{ dragging }">
          <div v-if="attachments.length" class="att-row">
            <div v-for="a in attachments" :key="a.key" class="att">
              <img :src="a.preview" alt="" />
              <div v-if="a.uploading" class="att-busy"><div class="spinner"></div></div>
              <button class="att-x" @click="removeAttachment(a)" title="Remove">✕</button>
            </div>
          </div>

          <div class="composer-row">
            <label class="icon-btn" title="Attach images (or paste / drop)">
              📎
              <input type="file" accept="image/png,image/jpeg,image/webp,image/gif" multiple hidden @change="addFiles($event.target.files); $event.target.value = ''" />
            </label>
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

    <!-- ── Lightbox ─────────────────────────────────────── -->
    <Teleport to="body">
      <div v-if="lightbox" class="lightbox" @click="lightbox = null">
        <img :src="lightbox.url" alt="" @click.stop />
        <p v-if="lightbox.prompt" class="lightbox-caption" @click.stop>{{ lightbox.prompt }}</p>
      </div>
    </Teleport>
  </div>
</template>

<style scoped>
.chat-layout {
  display: flex;
  height: 100vh;
  height: 100dvh;
  position: relative;
  background: var(--bg);
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

.library-link.active {
  background: rgba(108, 92, 231, 0.18);
  border-color: rgba(108, 92, 231, 0.4);
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
  flex: 1;
  min-height: 80px;
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
  display: flex;
  flex-direction: column;
  position: relative;
}

.chat-scroll {
  flex: 1;
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

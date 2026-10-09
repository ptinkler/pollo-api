<script setup>
import { computed, inject, nextTick, onBeforeUnmount, onMounted, provide, reactive, ref, watch } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'
import CharacterEditor from '../components/characters/CharacterEditor.vue'
import CharacterPicker from '../components/characters/CharacterPicker.vue'
import ChatBalances from '../components/chat/ChatBalances.vue'
import ChatComposer from '../components/chat/ChatComposer.vue'
import ChatMessage from '../components/chat/ChatMessage.vue'
import ChatWelcome from '../components/chat/ChatWelcome.vue'
import ConversationList from '../components/chat/ConversationList.vue'
import InstructionsDialog from '../components/chat/InstructionsDialog.vue'
import MediaLightbox from '../components/chat/MediaLightbox.vue'
import ModelPicker from '../components/chat/ModelPicker.vue'
import SidebarSection from '../components/chat/SidebarSection.vue'
import MediaPicker from '../components/media/MediaPicker.vue'
import { useAuth } from '../composables/useAuth'
import {
  cancelChatMessage,
  chatMediaUrl,
  createConversation,
  deleteChatExchange,
  editChatMessage,
  fetchChatModels,
  fetchChatStatus,
  fetchConversation,
  fetchConversationSpend,
  fetchDeleteInfo,
  forkConversation,
  pinChatMedia,
  regenerateChatMedia,
  retryChatMessage,
  sendChatMessage,
  switchChatBranch,
} from '../composables/useChat'
import { useChatAttachments } from '../composables/useChatAttachments'
import { upsert, useChatCharacters } from '../composables/useChatCharacters'
import { useChatInstructions } from '../composables/useChatInstructions'
import { useChatBalances } from '../composables/useChatBalances'
import { useChatList } from '../composables/useChatList'
import { IMAGE_STEPS, MEMORY_STEPS, MODES, useComposerSettings } from '../composables/useComposerSettings'
import { provideFolded } from '../composables/useFolded'
import { useMessagePolling } from '../composables/useMessagePolling'
import { shortModel } from '../utils/format'

const route = useRoute()
const router = useRouter()
const showToast = inject('showToast', () => {})
const { hasKey, showKeyModal } = useAuth()
provideFolded()

// ── Server state ─────────────────────────────────────────────────────
const configured = ref(true)
const providers = reactive({ openrouter: true, venice: false }) // which API keys the server has
const models = reactive({ text: [], image: [], video: [] })
provide('chatModels', models) // for "Try another model" on failed media
const modelsLoading = ref(true)
const conversation = ref(null)
const messages = ref([])
const loadingConv = ref(false)
const convId = computed(() => route.params.id || null)
const chatList = useChatList(showToast)

const settings = useComposerSettings(models)
const {
  selected,
  mode,
  memoryIndex,
  imageIndex,
  historyLimit,
  imageLimit,
  imageOpts,
  videoOpts,
  textInfo,
  imageInfo,
  videoInfo,
  imageRatioOptions,
  imageResOptions,
  videoRatioOptions,
  videoResOptions,
  durationOptions,
  showImageOpts,
  showVideoOpts,
  currentMode,
  activeModel,
  cycleMode,
  applyDefaults,
  applyChat,
  turnSettings,
} = settings

// ── Page state ───────────────────────────────────────────────────────
const draft = ref('')
const sending = ref(false)
const streamingId = ref(null)
const composer = ref(null)
const scroller = ref(null)
const messagesEl = ref(null)
const dragging = ref(false)
const sidebarOpen = ref(false)
const lightbox = ref(null)
const libraryOpen = ref(false)
let abort = null
let skipLoadFor = null

const { attachments, files, uploading, room, addFiles, addFromLibrary, addChatImage, ...attach } = useChatAttachments({
  convId,
  ensureConversation,
  showToast,
})

const { balances, refresh: refreshBalances } = useChatBalances(providers)
const polling = useMessagePolling({
  messages,
  streamingId,
  replace: replaceMessage,
  onFinished: () => {
    refreshBalances()
    refreshSpend(convId.value)
  },
})

// What the memory slider means for this chat: the new prompt plus earlier messages
const memoryHint = computed(() => {
  const total = messages.value.length + 1
  const limit = historyLimit.value
  const n = imageLimit.value
  const imgs = { null: 'every image', 0: 'no images', 1: 'the latest image' }[n] ?? `the ${n} most recent images`
  if (limit && limit < total) {
    const dropped = total - limit
    return `Sending the last ${limit} of ${total} messages plus ${imgs}; the oldest ${dropped === 1 ? 'one is' : `${dropped} are`} left out.`
  }
  return messages.value.length
    ? `Sending the whole chat (${total} messages) plus ${imgs}.`
    : `Sends up to ${limit ?? 'all'} messages plus ${imgs}.`
})

const takesImages = info => !!info?.input_modalities?.includes('image')
const hasAttachments = () => attachments.value.length > 0

// What's wrong with the current mode and models, first match wins
const MODE_WARNINGS = [
  {
    when: () => mode.value === 'image' && !selected.image,
    text: () => 'Pick an image model to use Image mode.',
  },
  {
    when: () => mode.value === 'video' && !selected.video,
    text: () => 'Pick a video model to use Video mode.',
  },
  {
    when: () => mode.value === 'image' && hasAttachments() && imageInfo.value && !takesImages(imageInfo.value),
    text: () =>
      `${imageInfo.value.name} can't take reference images — pick one tagged “edits” or “context” to use the attached image.`,
  },
  {
    when: () => mode.value === 'auto' && textInfo.value && !textInfo.value.supports_tools,
    text: () =>
      `${textInfo.value.name} can't call tools, so Auto mode will only chat. Use Image/Video mode, or pick a model tagged “tools”.`,
  },
  {
    when: () =>
      ['auto', 'text'].includes(mode.value) && hasAttachments() && textInfo.value && !takesImages(textInfo.value),
    text: () => `${textInfo.value.name} can't see images; it will only know you attached one.`,
  },
]
const modeWarning = computed(() => MODE_WARNINGS.find(w => w.when())?.text() ?? '')

const canSend = computed(
  () => !sending.value && (draft.value.trim() || files.value.length) && !uploading.value && !!activeModel.value,
)

// Images pinned as references on the shown branch (the server uses the same set)
const pinned = computed(() =>
  messages.value.flatMap(m =>
    (m.media || []).filter(i => i.pinned && i.kind === 'image').map(i => ({ msg: m, mediaId: i.id })),
  ),
)

const lastAssistantId = computed(() => {
  const last = messages.value[messages.value.length - 1]
  return last?.role === 'assistant' ? last.id : null
})

// The image or video options' current picks, for a folded heading
const optionsSummary = opts =>
  [opts.aspect_ratio || 'auto', opts.resolution, opts.duration && `${opts.duration}s`].filter(Boolean).join(' · ')

async function loadModels(refresh = false) {
  modelsLoading.value = true
  try {
    const data = await fetchChatModels(refresh)
    Object.assign(models, { text: data.text || [], image: data.image || [], video: data.video || [] })
    for (const [kind, err] of Object.entries(data.errors || {})) {
      showToast(`Couldn't load ${kind} models: ${err}`, 'error')
    }
    applyDefaults()
  } catch (e) {
    showToast(`Couldn't load models: ${e.message}`, 'error')
  } finally {
    modelsLoading.value = false
  }
}

// ── Custom instructions ──────────────────────────────────────────────
const instructionsOpen = ref(false)
const {
  instructions,
  instructionId,
  attachedInstruction,
  defaultInstructionId,
  loadInstructions,
  setInstruction,
  onInstructionsChanged,
} = useChatInstructions({ convId, conversation, showToast })
// Video models and non-conversational image models don't take instructions
const instructionsUnused = computed(
  () => mode.value === 'video' || (mode.value === 'image' && !imageInfo.value?.conversational),
)

// ── Characters ───────────────────────────────────────────────────────
const {
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
} = useChatCharacters({ convId, settings, ensureConversation, showToast })
const CHARACTER_USE = {
  auto: 'The chat model knows them and sends their description and images when it puts one in a picture.',
  image: 'Their descriptions and images go with every image.',
}

function characterFromImage(file) {
  lightbox.value = null
  newCharacter([{ kind: 'chat', conversationId: convId.value, file, preview: chatMediaUrl(convId.value, file) }])
}

// ── The open chat ────────────────────────────────────────────────────
async function refreshSpend(id) {
  if (!id) return
  try {
    const data = await fetchConversationSpend(id)
    if (conversation.value?.id === id) conversation.value.spend = data
  } catch {
    /* keeps the last figure */
  }
}

async function loadConversation(id) {
  polling.stop()
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
    const c = data.conversation
    conversation.value = c
    messages.value = data.messages
    instructionId.value = c.instruction_id ?? null
    characterIds.value = c.character_ids || []
    applyChat(c)
    document.title = `${c.title} — Chat`
    scrollToBottom(true)
    polling.ensure()
  } catch (e) {
    showToast(`Couldn't open chat: ${e.message}`, 'error')
    router.replace({ name: 'chat' })
  } finally {
    loadingConv.value = false
  }
}

watch(convId, id => {
  if (id && id === skipLoadFor) {
    skipLoadFor = null
    return
  }
  abort?.abort()
  attach.clear()
  loadConversation(id)
})

// The open chat's id, creating it first if this is a new chat
async function ensureConversation() {
  if (convId.value) return convId.value
  const conv = await createConversation({
    text_model: selected.text || null,
    image_model: selected.image || null,
    video_model: selected.video || null,
    instruction_id: instructionId.value, // explicit, so "None" sticks
    character_ids: characterIds.value,
  })
  conversation.value = conv
  chatList.add(conv)
  skipLoadFor = conv.id
  await router.replace({ name: 'chat-conversation', params: { id: conv.id } })
  return conv.id
}

function openConversation(id) {
  sidebarOpen.value = false
  router.push({ name: 'chat-conversation', params: { id } })
}

function newChat() {
  sidebarOpen.value = false
  // From a conversation *or* the Library — anywhere but the blank chat itself
  if (route.name !== 'chat') router.push({ name: 'chat' })
  draft.value = ''
  composer.value?.focus()
}

async function renameConversation(c) {
  const title = await chatList.rename(c)
  if (title && conversation.value?.id === c.id) conversation.value.title = title
}

async function removeConversation(c) {
  if ((await chatList.remove(c)) && c.id === convId.value) router.push({ name: 'chat' })
}

// Chat creations live in Media, with everything else (filtered to chats)
function openLibrary() {
  sidebarOpen.value = false
  router.push({ name: 'media', query: { origin: 'chat' } })
}

// ── Using what's in the chat ─────────────────────────────────────────
// "Picture / video from this image": attach an image already in this chat
// (generated or uploaded — however far up) and switch to Image or Video
// mode. Being attached to the new message also makes it the latest image,
// so Auto mode uses it too if the user switches back.
function useImage({ file, mode: target }) {
  lightbox.value = null
  if (!addChatImage(file)) return
  mode.value = target
  composer.value?.focus()
}

// "Picture / video from this reply": the reply (or the selected part) becomes
// the prompt, editable before sending. Anything already typed is kept.
function useText({ text, mode: target }) {
  if (!text) return
  draft.value = draft.value.trim() ? `${draft.value.trim()}\n\n${text}` : text
  mode.value = target
  composer.value?.focus({ end: true })
}

function useSuggestion(text) {
  draft.value = text
  mode.value = 'auto'
  composer.value?.focus()
}

function onDrop(e) {
  dragging.value = false
  addFiles(e.dataTransfer?.files || [])
}

// ── Sending ──────────────────────────────────────────────────────────
const messageIndex = id => messages.value.findIndex(m => m.id === id)

// Swap in a fresher copy of a shown message (matched by id)
function replaceMessage(fresh) {
  const i = messageIndex(fresh.id)
  if (i !== -1) messages.value.splice(i, 1, fresh)
}

// What each event of a streamed turn does to the shown chat
const TURN_EVENTS = {
  start(ev, tempUser) {
    if (ev.user_message) {
      // New message: swap out the optimistic copy. Edit: refresh it in place.
      const i = tempUser ? messages.value.indexOf(tempUser) : messageIndex(ev.user_message.id)
      if (i !== -1) messages.value.splice(i, 1, ev.user_message)
    }
    messages.value.push(ev.assistant_message)
    streamingId.value = ev.assistant_message.id
    scrollToBottom(true)
  },
  delta(ev) {
    const m = messages.value[messageIndex(streamingId.value)]
    if (m) m.content += ev.text
    scrollToBottom()
  },
  media(ev) {
    const m = messages.value[messageIndex(ev.message_id)]
    if (!m) return
    upsert(m.media || (m.media = []), ev.item)
    scrollToBottom()
  },
  characters(ev) {
    onCharactersUsed(ev.characters, ev.character_ids)
  },
  title(ev) {
    if (conversation.value) conversation.value.title = ev.title
    chatList.setTitle(convId.value, ev.title)
    document.title = `${ev.title} — Chat`
  },
  done(ev) {
    const i = messageIndex(streamingId.value)
    if (i !== -1 && ev.message) messages.value.splice(i, 1, ev.message)
  },
}

async function runTurn(fn, id, body, tempUser) {
  sending.value = true
  abort = new AbortController()
  let started = false
  const onEvent = ev => {
    started ||= ev.type === 'start'
    TURN_EVENTS[ev.type]?.(ev, tempUser)
  }
  try {
    await fn(id, body, onEvent, abort.signal)
  } catch (e) {
    // Once the reply has started, the server finishes it regardless of this
    // connection — a dropped stream (throttled background tab, network blip)
    // is recovered by polling in `finally`, so there's nothing to report
    if (e.name !== 'AbortError' && !started) turnFailed(e, id, body, tempUser)
  } finally {
    sending.value = false
    streamingId.value = null
    abort = null
    chatList.bump(id)
    polling.ensure()
    refreshBalances()
    refreshSpend(id)
  }
}

function turnFailed(e, id, body, tempUser) {
  showToast(e.message, 'error')
  // Edit/retry (they name a message_id) swap the branch optimistically — resync with the server
  if (body.message_id != null) loadConversation(id)
  else if (tempUser) messages.value = messages.value.filter(m => m !== tempUser)
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
  const sent = attachments.value.filter(a => a.file)
  const tempUser = reactive({
    id: `tmp-${Date.now()}`,
    role: 'user',
    content,
    status: 'done',
    media: sent.map(a => ({ id: a.key, kind: 'image', status: 'done', file: a.file })),
  })
  messages.value.push(tempUser)
  draft.value = ''
  attach.clear()
  composer.value?.autosize()
  scrollToBottom(true)
  await runTurn(sendChatMessage, id, { ...turnSettings(), content, attachments: sent.map(a => a.file) }, tempUser)
}

// Retry/edit add a new branch beside the message; the old one stays
// reachable with the ‹ 1/2 › arrows. Show the new branch right away.
async function retry(msg) {
  const i = messageIndex(msg.id)
  if (sending.value || i === -1) return
  messages.value = messages.value.slice(0, i)
  // The prompt's mode tag follows the latest run (the server updates it too)
  const prompt = messages.value[i - 1]
  if (prompt?.role === 'user') prompt.mode = mode.value
  await runTurn(retryChatMessage, convId.value, { ...turnSettings(), message_id: msg.id }, null)
}

async function editMessage(msg, content) {
  const i = messageIndex(msg.id)
  if (sending.value || i === -1) return
  const tempUser = reactive({ ...msg, id: `tmp-${Date.now()}`, content, mode: mode.value, siblings: [] })
  messages.value = [...messages.value.slice(0, i), tempUser]
  scrollToBottom(true)
  await runTurn(editChatMessage, convId.value, { ...turnSettings(), message_id: msg.id, content }, tempUser)
}

// Same as an edit with unchanged text: a new branch with a fresh reply
async function resendMessage(msg) {
  await editMessage(msg, msg.content || '')
}

function deleteQuestion({ other_versions: versions, other_messages: after }) {
  const plural = (n, word) => `${n} ${word}${n === 1 ? '' : 's'}`
  const removes = [versions && plural(versions, 'other version'), after && plural(after, 'message')].filter(Boolean)
  const where = versions ? ' that followed them' : ' on other branches'
  const extra = removes.length ? ` This also removes ${removes.join(' and ')}${after ? where : ''}.` : ''
  return `Delete this prompt and its reply?${extra} Images and videos stay in Media.`
}

// Show what the server returns after changing the chat's history
function showChat(data) {
  conversation.value = data.conversation
  messages.value = data.messages
}

// Remove a prompt and its reply; the models stop seeing them, media stays in the Library
async function deleteExchange(msg) {
  if (sending.value) return
  try {
    if (!confirm(deleteQuestion(await fetchDeleteInfo(msg.id)))) return
    showChat(await deleteChatExchange(msg.id))
  } catch (e) {
    showToast(e.message, 'error')
  }
}

async function switchBranch(messageId) {
  if (sending.value) return
  try {
    showChat(await switchChatBranch(convId.value, messageId))
    polling.ensure()
  } catch (e) {
    showToast(e.message, 'error')
  }
}

// Carry on down a different path in a new chat, leaving this one as it is
async function forkFrom(msg) {
  if (sending.value) return
  try {
    const conv = await forkConversation(convId.value, msg.id)
    chatList.add(conv)
    router.push({ name: 'chat-conversation', params: { id: conv.id } })
    showToast('Branched into a new chat', 'success')
  } catch (e) {
    showToast(e.message, 'error')
  }
}

// Retry a failed image/video in place (same or another model). The server
// runs it in the background; polling picks up the result.
async function regenerateMedia(msg, { mediaId, model }) {
  try {
    replaceMessage(await regenerateChatMedia(msg.id, mediaId, model))
    polling.ensure()
  } catch (e) {
    showToast(e.message, 'error')
  }
}

async function pinMedia(msg, { mediaId, pinned: on }) {
  try {
    const { media } = await pinChatMedia(msg.id, mediaId, on)
    // Keep the shown copy's other fields (it may be fresher than `msg`)
    const current = messages.value[messageIndex(msg.id)]
    if (current) replaceMessage({ ...current, media })
  } catch (e) {
    showToast(e.message, 'error')
  }
}

async function unpinAll() {
  for (const p of pinned.value) await pinMedia(p.msg, { mediaId: p.mediaId, pinned: false })
}

async function stop() {
  if (!streamingId.value) return
  try {
    await cancelChatMessage(streamingId.value)
  } catch {
    abort?.abort()
  }
}

// ── Scrolling ────────────────────────────────────────────────────────
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

onMounted(async () => {
  try {
    const status = await fetchChatStatus()
    configured.value = status.configured
    providers.openrouter = status.openrouter ?? status.configured
    providers.venice = !!status.venice
  } catch {
    /* 401 handled by auth prompt */
  }
  chatList.load()
  loadInstructions()
  loadConversation(convId.value)
  if (configured.value) loadModels()
  else modelsLoading.value = false
  refreshBalances()
  composer.value?.focus()
})

onBeforeUnmount(() => {
  abort?.abort()
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
        <SidebarSection id="models" title="Models" :summary="shortModel(selected.text) || '—'">
          <template #actions>
            <button class="mini-btn" title="Refresh model lists" :disabled="modelsLoading" @click="loadModels(true)">
              ⟳
            </button>
          </template>
          <ModelPicker
            v-for="kind in ['text', 'image', 'video']"
            :key="kind"
            v-model="selected[kind]"
            :models="models[kind]"
            :label="{ text: 'Chat', image: 'Image', video: 'Video' }[kind]"
            :icon="{ text: '💬', image: '🖼', video: '🎬' }[kind]"
            :kind="kind"
            :loading="modelsLoading"
          />
        </SidebarSection>

        <SidebarSection id="mode" title="Mode" :summary="`${currentMode.icon} ${currentMode.label}`">
          <div class="modes">
            <button
              v-for="m in MODES"
              :key="m.id"
              class="mode"
              :class="{ active: mode === m.id }"
              :title="m.hint"
              @click="mode = m.id"
            >
              {{ m.icon }} {{ m.label }}
            </button>
          </div>
          <p class="mode-hint">{{ currentMode.hint }}</p>
        </SidebarSection>

        <SidebarSection id="instructions" title="Instructions" :summary="attachedInstruction?.name || 'None'">
          <template #actions>
            <button class="mini-btn" title="Create and edit saved instructions" @click="instructionsOpen = true">
              Manage
            </button>
          </template>
          <select
            class="instruction-select"
            :value="instructionId ?? ''"
            aria-label="Custom instructions for this chat"
            @change="setInstruction($event.target.value === '' ? null : Number($event.target.value))"
          >
            <option value="">None</option>
            <option v-for="i in instructions" :key="i.id" :value="i.id">
              {{ i.name }}{{ i.is_default ? ' (default)' : '' }}
            </option>
          </select>
          <p v-if="attachedInstruction && instructionsUnused" class="mode-hint">
            {{ mode === 'video' ? 'Video models' : 'This image model' }} can't take instructions; they apply in Auto and
            Chat modes.
          </p>
        </SidebarSection>

        <SidebarSection id="characters" title="Characters" :summary="characterNames || 'None'">
          <template #actions>
            <button class="mini-btn" title="All characters" @click="router.push({ name: 'characters' })">Manage</button>
          </template>
          <template v-if="!characterSupport.ok">
            <p class="side-warn">{{ characterSupport.reason }}</p>
            <p v-if="attachedCharacters.length" class="mode-hint">
              {{ characterNames }} {{ attachedCharacters.length === 1 ? 'stays' : 'stay' }} attached and will be used
              again when you switch back.
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
            {{ CHARACTER_USE[mode] || 'The chat model knows them.' }}
          </p>
        </SidebarSection>

        <SidebarSection
          v-if="mode === 'auto' || mode === 'text'"
          id="memory"
          title="Memory"
          :summary="historyLimit ? `${historyLimit} messages` : 'All'"
          summary-always
        >
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
        </SidebarSection>

        <SidebarSection
          v-if="mode !== 'video'"
          id="images"
          title="Chat images"
          :summary="imageLimit === null ? 'All' : imageLimit"
          summary-always
        >
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
            Recent chat images the models see, and the most sent as references with a new picture. Character images
            always go on top. More helps consistency but makes bigger, pricier requests.
          </p>
        </SidebarSection>

        <SidebarSection v-if="showImageOpts" id="imageOpts" title="Image options" :summary="optionsSummary(imageOpts)">
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
        </SidebarSection>

        <SidebarSection v-if="showVideoOpts" id="videoOpts" title="Video options" :summary="optionsSummary(videoOpts)">
          <div class="opts">
            <select
              v-model="videoOpts.aspect_ratio"
              title="Aspect ratio (ignored when animating an image — the image sets it)"
            >
              <option value="">Ratio: auto</option>
              <option v-for="r in videoRatioOptions" :key="r" :value="r">{{ r }}</option>
            </select>
            <select
              v-if="videoResOptions.length"
              v-model="videoOpts.resolution"
              title="Resolution (Kling: quality tier)"
            >
              <option value="">Res: default</option>
              <option v-for="r in videoResOptions" :key="r" :value="r">{{ r }}</option>
            </select>
            <select v-if="durationOptions.length" v-model="videoOpts.duration" title="Duration">
              <option value="">Length: {{ mode === 'auto' ? 'auto' : 'default' }}</option>
              <option v-for="d in durationOptions" :key="d" :value="d">{{ d }}s</option>
            </select>
            <label v-if="videoInfo?.generate_audio" class="opt-check">
              <input v-model="videoOpts.generate_audio" type="checkbox" /> Audio
            </label>
          </div>
        </SidebarSection>
        <p v-if="mode === 'auto' && (showImageOpts || showVideoOpts)" class="mode-hint">
          In Auto mode these apply whenever the chat model makes an image or video. "auto" lets it choose.
        </p>

        <p v-if="modeWarning" class="side-warn">{{ modeWarning }}</p>
        <p v-if="!configured" class="side-warn">
          No chat provider is configured. Add <code>OPENROUTER_API_KEY</code> and/or <code>VENICE_API_KEY</code> to the
          server's <code>.env</code> and restart.
        </p>
      </div>

      <button class="library-link" title="Every image and video from your chats, in Media" @click="openLibrary">
        🗂 Media
      </button>

      <ConversationList
        :list="chatList"
        :active-id="convId"
        @open="openConversation"
        @rename="renameConversation"
        @remove="removeConversation"
      />

      <div class="side-bottom">
        <button
          class="mini-btn key"
          :class="{ missing: !hasKey }"
          :title="hasKey ? 'API key set — click to change' : 'No API key — click to set'"
          @click="showKeyModal = true"
        >
          🔑 {{ hasKey ? 'Signed in' : 'Sign in' }}
        </button>
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

      <ChatBalances :providers="providers" :balances="balances" :spend="conversation?.spend" />

      <div ref="scroller" class="chat-scroll" @scroll.passive="onScroll">
        <div v-if="loadingConv" class="center-note"><div class="spinner"></div></div>

        <ChatWelcome v-else-if="!messages.length" @suggest="useSuggestion" />

        <div v-else ref="messagesEl" class="messages">
          <div v-if="conversation?.forked_from" class="fork-origin">
            ⑂ Branched from
            <a
              v-if="conversation.forked_from.exists"
              href="#"
              @click.prevent="openConversation(conversation.forked_from.id)"
              >{{ conversation.forked_from.title }}</a
            >
            <span v-else>a chat that's since been deleted</span>
          </div>
          <ChatMessage
            v-for="m in messages"
            :key="m.id"
            :message="m"
            :conv-id="convId || ''"
            :can-retry="m.id === lastAssistantId && !sending"
            :can-edit="m.role === 'user' && typeof m.id === 'number' && !sending"
            :can-switch="!sending"
            :can-branch="typeof m.id === 'number' && !sending && m.status !== 'streaming'"
            @retry="retry(m)"
            @edit="content => editMessage(m, content)"
            @resend="resendMessage(m)"
            @branch="switchBranch"
            @use-image="useImage"
            @use-text="useText"
            @regenerate="payload => regenerateMedia(m, payload)"
            @pin="payload => pinMedia(m, payload)"
            @delete="deleteExchange(m)"
            @fork="forkFrom(m)"
            @open-chat="openConversation"
            @stop="stop"
            @open-media="item => (lightbox = item)"
          />
        </div>
      </div>

      <ChatComposer
        ref="composer"
        v-model="draft"
        :mode="currentMode"
        :attachments="attachments"
        :character-names="characterSupport.ok ? attachedCharacters.map(c => c.name) : []"
        :pinned-count="pinned.length"
        :sending="sending"
        :can-send="!!canSend"
        :dragging="dragging"
        @send="send"
        @stop="stop"
        @files="addFiles"
        @remove-attachment="attach.remove"
        @open-library="libraryOpen = true"
        @cycle-mode="cycleMode"
        @show-sidebar="sidebarOpen = true"
        @unpin-all="unpinAll"
      />
    </section>

    <MediaPicker
      :open="libraryOpen"
      title="Attach images"
      :max="Math.max(1, room())"
      @pick="addFromLibrary"
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

    <MediaLightbox
      :item="lightbox"
      @close="lightbox = null"
      @use-image="useImage"
      @make-character="characterFromImage"
    />
  </div>
</template>

<style scoped>
.chat-layout {
  display: flex;
  height: 100vh;
  height: 100dvh;
  position: relative;
  overflow: hidden; /* only the panes inside scroll, never the page */
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

/* Section headings fold their section away */

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

/* A pinned chat's pin always shows */

.fork-origin {
  align-self: center;
  font-size: 0.78rem;
  color: var(--text2);
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 999px;
  padding: 4px 12px;
}

.fork-origin a {
  color: var(--accent);
  text-decoration: none;
}

.fork-origin a:hover {
  text-decoration: underline;
}

.side-bottom {
  margin-top: auto; /* stays at the bottom when the chat list is folded */
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

/* ── Composer ────────────────────────── */

/* ── Lightbox ────────────────────────── */

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
}
</style>

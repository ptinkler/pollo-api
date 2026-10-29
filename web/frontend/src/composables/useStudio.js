import { ref, reactive, computed, watch } from 'vue'
import {
  fetchConversations,
  fetchConversation,
  fetchConversationSpend,
  fetchChatStatus,
  fetchSpaces,
  createSpace,
  updateSpace,
  deleteSpace,
  fetchChatModels,
  createConversation,
  patchConversation,
  deleteConversation,
  sendChatMessage,
  retryChatMessage,
  editChatMessage,
  regenerateChatMedia,
  pinChatMedia,
  deleteChatExchange,
  fetchDeleteInfo,
  switchChatBranch,
  forkConversation,
  cancelChatMessage,
} from './useChat'
import { upsert, useChatCharacters } from './useChatCharacters'
import { useChatInstructions } from './useChatInstructions'
import { useMessagePolling } from './useMessagePolling'
import { useChatAttachments } from './useChatAttachments'
import { useChatBalances } from './useChatBalances'
import { useChatDefaults } from './useChatDefaults'

// All of Studio's state + behaviour, kept out of the view so the components
// stay presentational. `settings` is a useComposerSettings() instance (shared
// with the inspector's model pickers); `models` is its catalogue, filled here.
export function useStudio({ models, settings, showToast }) {
  const { selected, mode, turnSettings, applyChat, applyDefaults } = settings

  const modelsLoading = ref(true)
  const providers = reactive({ openrouter: true, venice: false })
  const { balances, refresh: refreshBalances } = useChatBalances(providers)
  const threads = ref([])
  const spaces = ref([])
  const active = ref(null)
  const activeThread = ref(null)
  const messages = ref([])
  const loading = ref(false)
  const sending = ref(false)
  const streamingId = ref(null)
  const draft = ref('')
  const lightbox = ref(null)
  const spend = ref(null)
  let abort = null
  let forking = false

  // Image attachments (image-edit refs / video first frame) — reused chat layer
  const attach = useChatAttachments({ convId: active, ensureConversation: ensureThread, showToast })
  const { attachments, addFiles, addChatImage, remove: removeAttachment, clear: clearAttachments, uploading } = attach

  // Defaults (global + space) a thread inherits, less any hidden here, plus pauses
  const defaults = useChatDefaults()
  const { inherited: allInherited, globalSettings, loadDefaults, setCurrentSpace } = defaults
  const NO_HIDDEN = () => ({ character: [], instruction: [], instruction_group: [] })
  const NO_PAUSED = () => ({ instruction: [], instruction_group: [] })
  const hiddenDefaults = ref(NO_HIDDEN())
  const paused = ref(NO_PAUSED())
  const splitInherited = hidden =>
    Object.fromEntries(
      Object.entries(allInherited.value).map(([kind, list]) => [
        kind,
        list.filter(x => hidden === (hiddenDefaults.value[kind] || []).includes(x.id)),
      ]),
    )
  const inheritedDefaults = computed(() => splitInherited(false))
  const hiddenInherited = computed(() => splitInherited(true))
  const inheritedInstructionIds = computed(() => ({
    snippets: inheritedDefaults.value.instruction.map(x => x.id),
    groups: inheritedDefaults.value.instruction_group.map(x => x.id),
  }))
  const inheritedCharacterIds = computed(() => inheritedDefaults.value.character.map(x => x.id))
  const pausedInstructionIds = computed(() => ({
    snippets: paused.value.instruction,
    groups: paused.value.instruction_group,
  }))
  const DEFAULT_KIND = { snippet: 'instruction', group: 'instruction_group' }
  async function setDefaultHidden({ kind: picked, id }, hide) {
    const kind = DEFAULT_KIND[picked] || picked
    const ids = hiddenDefaults.value[kind].filter(x => x !== id)
    hiddenDefaults.value = { ...hiddenDefaults.value, [kind]: hide ? [...ids, id] : ids }
    if (!active.value) return
    try {
      await patchConversation(active.value, { hidden_defaults: hiddenDefaults.value })
    } catch (e) {
      showToast(`Couldn't update the thread: ${e.message}`, 'error')
    }
  }
  async function setPaused({ kind: picked, id }, pause) {
    const kind = DEFAULT_KIND[picked] || picked
    const ids = paused.value[kind].filter(x => x !== id)
    paused.value = { ...paused.value, [kind]: pause ? [...ids, id] : ids }
    if (!active.value) return
    try {
      await patchConversation(active.value, { paused_instructions: paused.value })
    } catch (e) {
      showToast(`Couldn't update the thread: ${e.message}`, 'error')
    }
  }
  // Tell the defaults singleton which space is in context (for editors' add-to toggles)
  watch(
    () => activeThread.value?.space_id ?? null,
    id => setCurrentSpace(id),
    { immediate: true },
  )

  // Instructions + characters attached to the thread (plus the inherited defaults)
  const instr = useChatInstructions({
    convId: active,
    conversation: activeThread,
    showToast,
    inherited: inheritedInstructionIds,
  })
  const {
    instructions,
    groups: instructionGroups,
    instructionIds,
    groupIds: instructionGroupIds,
    attachedInstructions,
    attachedGroups,
    attachmentSummary: instructionSummary,
    loadInstructions,
    setInstructions,
    setGroups,
    onInstructionUsed,
    onInstructionsChanged,
  } = instr
  const editingInstruction = ref(null)

  const chars = useChatCharacters({
    convId: active,
    settings,
    ensureConversation: ensureThread,
    showToast,
    inheritedIds: inheritedCharacterIds,
  })
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
  } = chars

  const messageIndex = id => messages.value.findIndex(m => m.id === id)
  const lastAssistantId = computed(() => {
    const last = messages.value[messages.value.length - 1]
    return last?.role === 'assistant' ? last.id : null
  })
  const canSend = computed(
    () => (!!draft.value.trim() || attachments.value.some(a => a.file)) && !uploading.value && !sending.value,
  )
  const activeTitle = computed(() => threads.value.find(t => t.id === active.value)?.title || 'New thread')

  function replaceMessage(fresh) {
    const i = messageIndex(fresh.id)
    if (i !== -1) messages.value.splice(i, 1, fresh)
  }
  function showChat(data) {
    if (data.conversation) activeThread.value = data.conversation
    messages.value = data.messages || []
  }

  const polling = useMessagePolling({ messages, streamingId, replace: replaceMessage, onFinished: () => loadLists() })

  // ── Loading ────────────────────────────────────────────────────────────
  async function loadModels() {
    modelsLoading.value = true
    try {
      const d = await fetchChatModels()
      Object.assign(models, { text: d.text || [], image: d.image || [], video: d.video || [] })
      applyDefaults()
    } catch {
      /* leave empty */
    } finally {
      modelsLoading.value = false
    }
  }
  async function loadLists() {
    try {
      const [c, s] = await Promise.all([fetchConversations(), fetchSpaces()])
      threads.value = c.conversations || c || []
      spaces.value = s.spaces || s || []
    } catch {
      /* auth prompt handles 401 */
    }
  }
  async function refreshSpend(id) {
    if (!id) {
      spend.value = null
      return
    }
    try {
      spend.value = await fetchConversationSpend(id)
    } catch {
      spend.value = null
    }
  }
  async function loadStatus() {
    try {
      const s = await fetchChatStatus()
      providers.openrouter = s.openrouter ?? s.configured
      providers.venice = !!s.venice
    } catch {
      /* ignore */
    }
    refreshBalances()
  }
  async function openThread(id) {
    active.value = id
    loading.value = true
    try {
      activeThread.value = await fetchConversation(id)
      messages.value = activeThread.value.messages || []
      applyChat(activeThread.value)
      instructionIds.value = activeThread.value.instruction_ids || []
      instructionGroupIds.value = activeThread.value.instruction_group_ids || []
      characterIds.value = activeThread.value.character_ids || []
      hiddenDefaults.value = { ...NO_HIDDEN(), ...activeThread.value.hidden_defaults }
      paused.value = { ...NO_PAUSED(), ...activeThread.value.paused_instructions }
      refreshSpend(id)
      polling.ensure()
    } catch {
      activeThread.value = null
      messages.value = []
    } finally {
      loading.value = false
    }
  }
  function newThread() {
    active.value = null
    activeThread.value = null
    messages.value = []
    instructionIds.value = []
    instructionGroupIds.value = []
    characterIds.value = []
    hiddenDefaults.value = NO_HIDDEN()
    paused.value = NO_PAUSED()
    spend.value = null
  }

  // ── Sending (same streamed-turn protocol as ChatView) ────────────────────
  const TURN_EVENTS = {
    start(ev, tempUser) {
      if (ev.user_message) {
        const i = tempUser ? messages.value.indexOf(tempUser) : messageIndex(ev.user_message.id)
        if (i !== -1) messages.value.splice(i, 1, ev.user_message)
      }
      messages.value.push(ev.assistant_message)
      streamingId.value = ev.assistant_message.id
    },
    delta(ev) {
      const m = messages.value[messageIndex(streamingId.value)]
      if (m) m.content += ev.text
    },
    media(ev) {
      const m = messages.value[messageIndex(ev.message_id)]
      if (m) upsert(m.media || (m.media = []), ev.item)
    },
    characters(ev) {
      onCharactersUsed(ev.characters || [], ev.character_ids || [])
    },
    instructions(ev) {
      onInstructionUsed(ev.instruction, ev.instruction_ids || [])
    },
    title(ev) {
      if (activeThread.value) activeThread.value.title = ev.title
      const t = threads.value.find(x => x.id === active.value)
      if (t) t.title = ev.title
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
      if (e.name === 'AbortError' || started) return
      showToast(e.message, 'error')
      if (body.message_id != null) openThread(id)
      else if (tempUser) messages.value = messages.value.filter(m => m !== tempUser)
    } finally {
      sending.value = false
      streamingId.value = null
      abort = null
      polling.ensure()
      loadLists()
      refreshSpend(active.value)
    }
  }

  async function ensureThread() {
    if (active.value) return active.value
    const conv = await createConversation({
      text_model: selected.text || null,
      image_model: selected.image || null,
      video_model: selected.video || null,
      instruction_ids: instructionIds.value,
      instruction_group_ids: instructionGroupIds.value,
      character_ids: characterIds.value,
      hidden_defaults: hiddenDefaults.value,
      paused_instructions: paused.value,
    })
    threads.value.unshift(conv)
    active.value = conv.id
    activeThread.value = conv
    messages.value = []
    return conv.id
  }

  async function send() {
    if (!canSend.value) return
    const content = draft.value.trim()
    const sent = attachments.value.filter(a => a.file)
    const id = await ensureThread()
    const tempUser = reactive({
      id: `tmp-${Date.now()}`,
      role: 'user',
      content,
      status: 'done',
      media: sent.map(a => ({ id: a.key, kind: 'image', status: 'done', file: a.file })),
    })
    messages.value.push(tempUser)
    draft.value = ''
    clearAttachments()
    await runTurn(sendChatMessage, id, { ...turnSettings(), content, attachments: sent.map(a => a.file) }, tempUser)
  }

  // ── Message actions ──────────────────────────────────────────────────────
  async function retry(msg) {
    const i = messageIndex(msg.id)
    if (sending.value || i === -1) return
    messages.value = messages.value.slice(0, i)
    await runTurn(retryChatMessage, active.value, { ...turnSettings(), message_id: msg.id }, null)
  }
  async function editMessage(msg, content) {
    const i = messageIndex(msg.id)
    if (sending.value || i === -1) return
    const tempUser = reactive({ ...msg, id: `tmp-${Date.now()}`, content, siblings: [] })
    messages.value = [...messages.value.slice(0, i), tempUser]
    await runTurn(editChatMessage, active.value, { ...turnSettings(), message_id: msg.id, content }, tempUser)
  }
  const resendMessage = msg => editMessage(msg, msg.content || '')

  function deleteQuestion({ other_versions: versions, other_messages: after }) {
    const plural = (n, word) => `${n} ${word}${n === 1 ? '' : 's'}`
    const removes = [versions && plural(versions, 'other version'), after && plural(after, 'message')].filter(Boolean)
    const where = versions ? ' that followed them' : ' on other branches'
    const extra = removes.length ? ` This also removes ${removes.join(' and ')}${after ? where : ''}.` : ''
    return `Delete this prompt and its reply?${extra} Images and videos stay in Media.`
  }
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
      showChat(await switchChatBranch(active.value, messageId))
      polling.ensure()
    } catch (e) {
      showToast(e.message, 'error')
    }
  }
  async function forkFrom(msg) {
    if (sending.value || forking) return
    forking = true
    showToast('Branching into a new thread…', 'info')
    try {
      const conv = await forkConversation(active.value, msg.id)
      threads.value.unshift(conv)
      await openThread(conv.id)
      showToast('Branched into a new thread', 'success')
    } catch (e) {
      showToast(e.message, 'error')
    } finally {
      forking = false
    }
  }
  async function regenerateMedia(msg, { mediaId, model }) {
    if (!model) {
      const kind = (msg.media || []).find(i => i.id === mediaId)?.kind
      if (kind && selected[kind]) model = selected[kind]
    }
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
      const current = messages.value[messageIndex(msg.id)]
      if (current) replaceMessage({ ...current, media })
    } catch (e) {
      showToast(e.message, 'error')
    }
  }
  async function stop() {
    if (!streamingId.value) return
    try {
      await cancelChatMessage(streamingId.value)
    } catch {
      abort?.abort()
    }
  }
  // "Animate / edit this image" and "picture/video from this reply": attach the
  // image (or append the text) and switch to the chosen mode
  function useImage({ file, mode: target } = {}) {
    lightbox.value = null
    if (file && !addChatImage(file)) return
    if (target) mode.value = target
  }
  function useText({ text, mode: target } = {}) {
    if (text) draft.value = draft.value.trim() ? `${draft.value.trim()}\n\n${text}` : text
    if (target) mode.value = target
  }

  // ── Thread management ────────────────────────────────────────────────────
  async function toggleFav(t) {
    const next = !t.pinned
    try {
      await patchConversation(t.id, { pinned: next })
      t.pinned = next
    } catch (e) {
      showToast(e.message, 'error')
    }
  }
  async function renameThread(t) {
    const name = prompt('Rename thread', t.title || '')
    if (name == null) return
    try {
      await patchConversation(t.id, { title: name.trim() })
      t.title = name.trim()
    } catch (e) {
      showToast(e.message, 'error')
    }
  }
  async function removeThread(t) {
    if (!confirm(`Delete “${t.title || 'Untitled'}”? Its images and videos stay in Media.`)) return
    try {
      await deleteConversation(t.id)
      threads.value = threads.value.filter(x => x.id !== t.id)
      if (active.value === t.id) newThread()
    } catch (e) {
      showToast(e.message, 'error')
    }
  }
  async function moveThread(t, spaceId) {
    try {
      await patchConversation(t.id, { space_id: spaceId })
      t.space_id = spaceId
    } catch (e) {
      showToast(e.message, 'error')
    }
  }

  // ── Space management ─────────────────────────────────────────────────────
  async function addSpace() {
    const name = prompt('New space name')
    if (!name?.trim()) return
    try {
      const space = await createSpace({ name: name.trim() })
      spaces.value = [...spaces.value, space]
    } catch (e) {
      showToast(e.message, 'error')
    }
  }
  async function renameSpace(s) {
    const name = prompt('Rename space', s.name || '')
    if (name == null) return
    try {
      await updateSpace(s.id, { name: name.trim() })
      s.name = name.trim()
    } catch (e) {
      showToast(e.message, 'error')
    }
  }
  async function removeSpace(s) {
    if (!confirm(`Delete space “${s.name}”? Its threads move to Unfiled.`)) return
    try {
      await deleteSpace(s.id)
      await loadLists()
    } catch (e) {
      showToast(e.message, 'error')
    }
  }

  return {
    modelsLoading,
    threads,
    spaces,
    active,
    activeThread,
    messages,
    loading,
    sending,
    streamingId,
    draft,
    lightbox,
    attachments,
    uploading,
    addFiles,
    removeAttachment,
    lastAssistantId,
    canSend,
    activeTitle,
    // instructions
    instructions,
    instructionGroups,
    instructionIds,
    instructionGroupIds,
    attachedInstructions,
    attachedGroups,
    instructionSummary,
    loadInstructions,
    setInstructions,
    setGroups,
    onInstructionsChanged,
    editingInstruction,
    // defaults (inherited / hidden / paused)
    inheritedDefaults,
    hiddenInherited,
    pausedInstructionIds,
    setDefaultHidden,
    setPaused,
    loadDefaults,
    globalSettings,
    // characters
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
    onCharacterSaved,
    onCharacterDeleted,
    providers,
    balances,
    spend,
    loadStatus,
    loadModels,
    loadLists,
    openThread,
    newThread,
    send,
    retry,
    editMessage,
    resendMessage,
    switchBranch,
    forkFrom,
    regenerateMedia,
    pinMedia,
    stop,
    deleteExchange,
    useImage,
    useText,
    toggleFav,
    renameThread,
    removeThread,
    moveThread,
    addSpace,
    renameSpace,
    removeSpace,
  }
}

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
  enhanceChatPrompt,
  estimateChatCost,
  pinChatMedia,
  favouriteChatMedia,
  fetchChatLibrary,
  deleteChatExchange,
  fetchDeleteInfo,
  switchChatBranch,
  forkConversation,
  cancelChatMessage,
} from './useChat'
import { upsert, useChatCharacters } from './useChatCharacters'
import { useChatInstructions } from './useChatInstructions'
import { useMessagePolling } from './useMessagePolling'
import { useChatAttachments, MAX_ATTACHMENTS } from './useChatAttachments'
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
  // Threads with a live turn: generation blocks only its own thread, not the app
  const sendingIds = ref(new Set())
  // Which lane the composer feeds: 'gallery' sends are standalone exchanges that
  // never block (or join) the chat, so the gallery view is never "sending".
  const lane = ref(null)
  const sending = computed(() => lane.value !== 'gallery' && sendingIds.value.has(active.value))
  const streamingId = ref(null)
  const draft = ref('')
  const lightbox = ref(null)
  const spend = ref(null)
  const favourites = ref([]) // cross-thread gallery of favourited generations
  // The thread being created from scratch opens on this view ('chat' | 'gallery')
  const newKind = ref('chat')
  const aborts = new Map() // thread id -> AbortController of its live turn
  let forking = false

  // Image attachments (image-edit refs / video first frame) — reused chat layer
  // Images the next message may carry: a video model takes one start frame (two with
  // first+last frame) unless it's a reference-image model; others take the usual max
  const imageLimit = () => {
    if (mode.value !== 'video') return MAX_ATTACHMENTS
    const v = settings.videoInfo.value
    if (!v) return MAX_ATTACHMENTS
    // Reference-to-video: as many images as the model's ref_mode allows.
    if (v.ref_mode) return v.ref_mode.limits?.image ?? v.ref_mode.max ?? MAX_ATTACHMENTS
    if (v.reference_images) return v.max_refs || MAX_ATTACHMENTS
    return v.frame_images?.includes('last_frame') ? 2 : 1
  }
  // Video / audio reference caps — a ref_mode model takes several (its per-type
  // limit); everything else takes one.
  const refTypeLimit = kind => {
    const v = mode.value === 'video' ? settings.videoInfo.value : null
    return v?.ref_mode ? (v.ref_mode.limits?.[kind] ?? v.ref_mode.max ?? 1) : 1
  }
  const attach = useChatAttachments({
    convId: active,
    ensureConversation: ensureThread,
    showToast,
    limit: imageLimit,
    videoLimit: () => refTypeLimit('video'),
    audioLimit: () => refTypeLimit('audio'),
  })
  const {
    attachments,
    addFiles,
    addFromLibrary,
    addChatImage,
    remove: removeAttachment,
    clear: clearAttachments,
    uploading,
  } = attach

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
    const last = messages.value.filter(m => !m.lane).at(-1)
    return last?.role === 'assistant' ? last.id : null
  })
  const canSend = computed(
    () =>
      (!!draft.value.trim() || attachments.value.some(a => a.file) || !!settings.activeInfo.value?.no_prompt) &&
      !uploading.value &&
      !sending.value,
  )
  const activeTitle = computed(() => threads.value.find(t => t.id === active.value)?.title || 'New thread')
  // Which view the current thread opens on. A saved thread carries its own
  // kind; an unsaved new thread uses the kind picked in the sidebar.
  const activeKind = computed(() => (active.value ? activeThread.value?.kind || 'chat' : newKind.value))

  function replaceMessage(fresh) {
    const i = messageIndex(fresh.id)
    if (i !== -1) messages.value.splice(i, 1, fresh)
  }
  function showChat(data) {
    if (data.conversation) activeThread.value = data.conversation
    messages.value = data.messages || []
  }

  const polling = useMessagePolling({ messages, streamingId, replace: replaceMessage, onFinished: refreshAfterBilling })

  // Something was billed (a reply or generation landed): refresh every figure
  // that depends on it instead of waiting for a reload
  function refreshAfterBilling() {
    loadLists()
    refreshSpend(active.value)
    refreshBalances()
  }
  // Balances also drift outside this tab (other devices, other chats): re-check
  // when the tab is shown again and every couple of minutes while it is.
  const onShown = () => document.visibilityState === 'visible' && refreshBalances()
  document.addEventListener('visibilitychange', onShown)
  setInterval(onShown, 120000)

  async function loadModels() {
    modelsLoading.value = true
    try {
      const d = await fetchChatModels()
      Object.assign(models, { text: d.text || [], image: d.image || [], video: d.video || [], audio: d.audio || [] })
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
      // GET returns { conversation, messages }; unwrap so activeThread holds the
      // conversation itself (its kind/settings/instructions live there, not on
      // the envelope). showChat does the same during a streamed turn.
      const data = await fetchConversation(id)
      const conv = data.conversation || data
      activeThread.value = conv
      messages.value = data.messages || []
      applyChat(conv)
      instructionIds.value = conv.instruction_ids || []
      instructionGroupIds.value = conv.instruction_group_ids || []
      characterIds.value = conv.character_ids || []
      hiddenDefaults.value = { ...NO_HIDDEN(), ...conv.hidden_defaults }
      paused.value = { ...NO_PAUSED(), ...conv.paused_instructions }
      refreshSpend(id)
      polling.ensure()
      return true
    } catch {
      // The thread doesn't exist (e.g. a stale URL) — fall back to a clean new
      // thread rather than leaving `active` pointing at a bad id, which would
      // make every later action 404 ("Conversation not found").
      newThread()
      return false
    } finally {
      loading.value = false
    }
  }
  function newThread(kind = 'chat') {
    active.value = null
    activeThread.value = null
    messages.value = []
    instructionIds.value = []
    instructionGroupIds.value = []
    characterIds.value = []
    hiddenDefaults.value = NO_HIDDEN()
    paused.value = NO_PAUSED()
    spend.value = null
    newKind.value = kind === 'gallery' ? 'gallery' : 'chat'
  }
  // Switch a thread between Chat and Gallery (its default landing view).
  async function setThreadKind(kind) {
    const k = kind === 'gallery' ? 'gallery' : 'chat'
    if (!active.value) {
      newKind.value = k
      return
    }
    try {
      await patchConversation(active.value, { kind: k })
      if (activeThread.value) activeThread.value.kind = k
      const t = threads.value.find(x => x.id === active.value)
      if (t) t.kind = k
    } catch (e) {
      showToast(e.message, 'error')
    }
  }

  // Sending (same streamed-turn protocol as ChatView)
  const TURN_EVENTS = {
    start(ev, tempUser) {
      if (ev.user_message) {
        const i = tempUser ? messages.value.indexOf(tempUser) : messageIndex(ev.user_message.id)
        if (i !== -1) messages.value.splice(i, 1, ev.user_message)
      }
      messages.value.push(ev.assistant_message)
      if (!ev.assistant_message.lane) streamingId.value = ev.assistant_message.id
    },
    delta(ev) {
      const m = messages.value[messageIndex(streamingId.value)]
      if (m) m.content += ev.text
    },
    media(ev) {
      const m = messages.value[messageIndex(ev.message_id)]
      if (!m) return
      const list = m.media || (m.media = [])
      const prev = list.find(x => x.id === ev.item.id)
      upsert(list, ev.item)
      // Flipped pending → done: announce it (the gallery queue has no toast of its own).
      if (ev.item.status === 'done' && (!prev || prev.status === 'pending')) {
        showToast(`${ev.item.kind === 'video' ? 'Video' : 'Image'} ready`, 'success')
        refreshAfterBilling()
      }
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
      const i = messageIndex(ev.message?.id)
      if (i !== -1) messages.value.splice(i, 1, ev.message)
    },
  }

  const setSending = (id, on) => {
    const next = new Set(sendingIds.value)
    if (on) next.add(id)
    else next.delete(id)
    sendingIds.value = next
  }

  async function runTurn(fn, id, body, tempUser) {
    const gallery = body.lane === 'gallery'
    if (!gallery) setSending(id, true)
    const ctl = new AbortController()
    if (!gallery) aborts.set(id, ctl)
    let started = false
    // Once the user opens another thread the stream must not touch the shown
    // messages; the server keeps going and polling picks the result up.
    const onEvent = ev => {
      started ||= ev.type === 'start'
      if (active.value === id && !(gallery && ev.type === 'delta')) TURN_EVENTS[ev.type]?.(ev, tempUser)
    }
    try {
      await fn(id, body, onEvent, ctl.signal)
    } catch (e) {
      if (e.name === 'AbortError' || started) return
      showToast(e.message, 'error')
      if (active.value !== id) return
      if (body.message_id != null) openThread(id)
      else if (tempUser) messages.value = messages.value.filter(m => m !== tempUser)
    } finally {
      if (!gallery) {
        setSending(id, false)
        aborts.delete(id)
        if (active.value === id) streamingId.value = null
      }
      polling.ensure()
      refreshAfterBilling()
    }
  }

  async function ensureThread() {
    if (active.value) return active.value
    const conv = await createConversation({
      kind: newKind.value,
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
    const nImages = sent.filter(a => !a.video && !a.audio).length
    if (nImages > imageLimit()) {
      return showToast(
        `This video model takes ${imageLimit()} image${imageLimit() === 1 ? '' : 's'} — remove some, or pick a reference-image model (e.g. a “Ref” model)`,
        'error',
      )
    }
    const id = await ensureThread()
    const tempUser = reactive({
      id: `tmp-${Date.now()}`,
      role: 'user',
      content,
      lane: lane.value,
      status: 'done',
      media: sent.map(a => ({
        id: a.key,
        kind: a.audio ? 'audio' : a.video ? 'video' : 'image',
        status: 'done',
        file: a.file,
      })),
    })
    messages.value.push(tempUser)
    draft.value = ''
    clearAttachments()
    await runTurn(
      sendChatMessage,
      id,
      { ...turnSettings(), content, attachments: sent.map(a => a.file), lane: lane.value },
      tempUser,
    )
  }

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
  // Deleting works on the prompt; given a reply (the gallery hands us the
  // message holding the media) it deletes the prompt that produced it.
  async function deleteExchange(msg) {
    if (sending.value) return
    const promptId = msg.role === 'assistant' && msg.parent_id ? msg.parent_id : msg.id
    try {
      if (!confirm(deleteQuestion(await fetchDeleteInfo(promptId)))) return
      showChat(await deleteChatExchange(promptId))
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
  // "Use settings" (gallery): fill the composer from a past generation so the
  // user can tweak and press Generate. Fills only — never fires (unlike retry).
  function applyGenerationSettings(item) {
    const kind = ['video', 'audio'].includes(item.kind) ? item.kind : 'image'
    const text = item.original_prompt || item.prompt
    if (text) draft.value = text
    const model = item.model || item.params?.model
    if (model) selected[kind] = model
    mode.value = kind
    applyOptions(kind, item.params || {})
    restoreRefs(item)
  }
  const AUDIO_KEYS = [
    'voice',
    'speed',
    'volume',
    'pitch',
    'instrumental',
    'vocal_gender',
    'style',
    'title',
    'negative_prompt',
    'duration',
  ]
  function applyOptions(kind, p) {
    if (kind === 'audio') {
      for (const k of AUDIO_KEYS) if (p[k] != null) settings.audioOpts[k] = p[k]
      return
    }
    const opts = kind === 'video' ? settings.videoOpts : settings.imageOpts
    for (const k of ['aspect_ratio', 'resolution']) if (p[k]) opts[k] = p[k]
    if (kind !== 'video') return
    for (const k of ['duration', 'generate_audio']) if (p[k] != null) opts[k] = p[k]
  }
  // Put a generation's reference images back as attachments (character refs
  // come back with the characters, not as files)
  function restoreRefs(item) {
    clearAttachments()
    const p = item.params || {}
    const files = [...(p.refs || []), p.first_frame, p.last_frame].filter(f => f && !f.startsWith('char:'))
    for (const f of new Set(files)) addChatImage(f, item.conversation_id)
  }
  // Pollo's own price for what's set up in the composer (Pollo models only)
  const estimate = ref(null)
  let estimateTimer = null
  let estimateSeq = 0
  async function refreshEstimate() {
    const kind = mode.value
    const model = ['image', 'video', 'audio'].includes(kind) ? selected[kind] : null
    const seq = ++estimateSeq
    if (!model?.startsWith('pollo/')) {
      estimate.value = null
      return
    }
    const t = turnSettings()
    const o = { video: t.video_options, audio: {}, image: t.image_options }[kind]
    const audio = kind === 'audio' ? { prompt: draft.value.trim(), audio_options: t.audio_options } : {}
    try {
      const r = await estimateChatCost({
        model,
        kind,
        ...o,
        ...audio,
        n_images: attachments.value.filter(a => !a.video && !a.audio).length,
      })
      if (seq === estimateSeq) estimate.value = r.estimate
    } catch {
      if (seq === estimateSeq) estimate.value = null
    }
  }
  watch(
    () =>
      JSON.stringify([
        mode.value,
        selected.image,
        selected.video,
        selected.audio,
        turnSettings(),
        attachments.value.length,
        mode.value === 'audio' ? draft.value : '',
      ]),
    () => {
      clearTimeout(estimateTimer)
      estimateTimer = setTimeout(refreshEstimate, 400)
    },
    { immediate: true },
  )
  // Enhance button: rewrite the draft with the text model. Only on request —
  // sending never alters the prompt.
  const enhancing = ref(false)
  async function enhanceDraft() {
    const prompt = draft.value.trim()
    if (!prompt || enhancing.value) return
    if (!selected.text) return showToast('Pick a text model to enhance prompts', 'error')
    enhancing.value = true
    try {
      const r = await enhanceChatPrompt({
        prompt,
        model: selected.text,
        kind: mode.value === 'video' ? 'video' : 'image',
      })
      draft.value = r.prompt
    } catch (e) {
      showToast(e.message, 'error')
    } finally {
      enhancing.value = false
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
  // Star/un-star a generation (bookmark for the Favourites gallery). `msg` may
  // be a real message (in-thread) or a library row carrying { message_id }.
  async function favouriteMedia(msg, { mediaId, favourite: on }) {
    const messageId = msg.id ?? msg.message_id
    try {
      const { media } = await favouriteChatMedia(messageId, mediaId, on)
      const current = messages.value[messageIndex(messageId)]
      if (current) replaceMessage({ ...current, media })
      // Reflect it in the open favourites gallery without a full reload
      const f = favourites.value.find(i => i.id === mediaId)
      if (f) f.favourite = on
      if (!on) favourites.value = favourites.value.filter(i => i.id !== mediaId)
    } catch (e) {
      showToast(e.message, 'error')
    }
  }
  async function loadFavourites() {
    try {
      const { items } = await fetchChatLibrary()
      favourites.value = (items || []).filter(i => i.favourite && i.file)
    } catch {
      favourites.value = []
    }
  }
  async function stop() {
    if (!streamingId.value) return
    try {
      await cancelChatMessage(streamingId.value)
    } catch {
      aborts.get(active.value)?.abort()
    }
  }
  // "Animate / edit this image" and "picture/video from this reply": attach the
  // image (or append the text) and switch to the chosen mode
  function useImage({ file, mode: target, conversation_id: fromConv } = {}) {
    lightbox.value = null
    if (file && !addChatImage(file, fromConv)) return
    if (target) mode.value = target
  }
  function useText({ text, mode: target } = {}) {
    if (text) draft.value = draft.value.trim() ? `${draft.value.trim()}\n\n${text}` : text
    if (target) mode.value = target
  }

  async function toggleFav(t) {
    const next = !t.pinned
    try {
      await patchConversation(t.id, { pinned: next })
      t.pinned = next
    } catch (e) {
      showToast(e.message, 'error')
    }
  }
  // Rename from the sidebar's inline editor (no prompt). `name` is the new title.
  async function renameThread(t, name) {
    const title = (name ?? '').trim()
    if (!title || title === (t.title || '')) return
    try {
      await patchConversation(t.id, { title })
      t.title = title
      if (activeThread.value?.id === t.id) activeThread.value.title = title
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
  async function renameSpace(s, name) {
    if (!name?.trim()) return
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
    estimate,
    lane,
    streamingId,
    draft,
    lightbox,
    attachments,
    uploading,
    addFiles,
    addFromLibrary,
    enhancing,
    enhanceDraft,
    removeAttachment,
    lastAssistantId,
    canSend,
    activeTitle,
    activeKind,
    newKind,
    favourites,
    loadFavourites,
    favouriteMedia,
    setThreadKind,
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
    applyGenerationSettings,
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

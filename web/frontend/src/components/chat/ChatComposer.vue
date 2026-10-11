<script setup>
import { computed, nextTick, ref, watch } from 'vue'
import { takeFiles } from '../../utils/files'

// The message box: attachments, what goes with the message (characters,
// pinned images), and one row of controls. v-model is the draft.
const draft = defineModel({ type: String, required: true })
const props = defineProps({
  mode: { type: Object, required: true }, // the current MODES entry
  attachments: { type: Array, required: true }, // from useChatAttachments
  characterNames: { type: Array, default: () => [] }, // attached characters in use
  pinnedCount: { type: Number, default: 0 },
  // The next image's reference images (ChatView's refTray), or null for none
  refs: { type: Object, default: null },
  sending: { type: Boolean, default: false },
  canSend: { type: Boolean, default: false },
  dragging: { type: Boolean, default: false },
})
const emit = defineEmits([
  'send',
  'stop',
  'files',
  'remove-attachment',
  'open-library',
  'cycle-mode',
  'show-sidebar',
  'unpin-all',
  'toggle-ref',
  'reset-refs',
])

const textarea = ref(null)
const trayOpen = ref(false)
// The left-out references the user was last warned about (a send goes ahead once they've seen them)
const warnedAbout = ref('')

const leftOut = computed(() => props.refs?.dropped ?? [])
const refsTitle = computed(() => {
  const r = props.refs
  if (!r) return ''
  const of = r.max ? `${r.sent} of the ${r.max} this image model takes` : `${r.sent}`
  return leftOut.value.length
    ? `${leftOut.value.length} reference image${leftOut.value.length !== 1 ? 's' : ''} won't fit — click to choose`
    : `Reference images: ${of} — click to choose`
})

watch(
  () => props.refs,
  r => {
    if (!r) trayOpen.value = false
  },
)

// Sending with references that won't fit: show them first, once
function trySend() {
  const sig = leftOut.value.join('|')
  if (sig && sig !== warnedAbout.value && !props.sending && props.canSend) {
    warnedAbout.value = sig
    trayOpen.value = true
    return
  }
  emit('send')
}

const STATE_TITLES = {
  sent: 'Sent — click to leave it out',
  dropped: "Won't fit the image model — click to send it instead of a later one",
  off: 'Left out — click to send it',
  capped: 'Over the image slider — click to send it',
}

const placeholder = computed(
  () =>
    ({
      image: 'Describe an image…',
      video: 'Describe a video (attach an image to animate it)…',
    })[props.mode.id] ?? 'Message, or ask for an image or video…',
)

// Grow with the text, up to a limit
function autosize() {
  nextTick(() => {
    const el = textarea.value
    if (!el) return
    el.style.height = 'auto'
    el.style.height = `${Math.min(el.scrollHeight, 240)}px`
  })
}

function focus({ end = false } = {}) {
  autosize()
  nextTick(() => {
    textarea.value?.focus()
    if (end) textarea.value?.setSelectionRange(draft.value.length, draft.value.length)
  })
}

function onKeydown(e) {
  if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) {
    e.preventDefault()
    trySend()
  }
}

// Some browsers put a pasted screenshot only in the clipboard's items, not its files
function pastedFiles(data) {
  const files = [...(data?.files || [])]
  if (files.length) return files
  return [...(data?.items || [])]
    .filter(i => i.kind === 'file')
    .map(i => i.getAsFile())
    .filter(Boolean)
}

function onPaste(e) {
  const files = pastedFiles(e.clipboardData)
  if (files.some(f => f.type.startsWith('image/'))) {
    e.preventDefault()
    emit('files', files)
  }
}

defineExpose({ focus, autosize })
</script>

<template>
  <div class="composer-wrap">
    <div class="composer" :class="{ dragging }">
      <div v-if="attachments.length" class="att-row">
        <div v-for="a in attachments" :key="a.key" class="att">
          <img :src="a.preview" alt="" />
          <div v-if="a.uploading" class="att-busy"><div class="spinner"></div></div>
          <button class="att-x" title="Remove" @click="emit('remove-attachment', a)">✕</button>
        </div>
      </div>

      <div v-if="refs && trayOpen" class="ref-tray">
        <div class="ref-head">
          <span :class="{ warn: leftOut.length }">
            <template v-if="leftOut.length">
              ⚠ {{ leftOut.length }} won't fit — {{ refs.max }} max for this image model. Pick which go, or send again
              to send these {{ refs.sent }}.
            </template>
            <template v-else>Sending {{ refs.sent }}{{ refs.max ? ` of ${refs.max} max` : '' }}.</template>
            <template v-if="refs.guess"> In Auto mode the chat model picks the characters in each picture.</template>
          </span>
          <button
            v-if="refs.customised"
            class="ref-link"
            title="Back to the automatic picks"
            @click="emit('reset-refs')"
          >
            Reset
          </button>
          <button class="ctx-x" title="Close" @click="trayOpen = false">✕</button>
        </div>
        <div v-for="g in refs.groups" :key="g.label" class="ref-group">
          <span class="ref-label">{{ g.label }}</span>
          <button
            v-for="it in g.items"
            :key="it.ref"
            class="ref"
            :class="[it.state, { forced: it.forced }]"
            :title="STATE_TITLES[it.state]"
            @click="emit('toggle-ref', it)"
          >
            <img :src="it.url" alt="" loading="lazy" />
            <span class="ref-badge">{{ it.state === 'sent' ? it.order : it.state === 'off' ? '✕' : '–' }}</span>
          </button>
        </div>
      </div>

      <div class="composer-row">
        <label class="icon-btn" title="Attach images (or paste / drop)">
          📎
          <input
            type="file"
            accept="image/png,image/jpeg,image/webp,image/gif"
            multiple
            hidden
            @change="emit('files', takeFiles($event))"
          />
        </label>
        <button class="icon-btn" title="Attach from your uploads and creations" @click="emit('open-library')">🗂</button>
        <button class="mode-chip" :title="`Mode: ${mode.label} — click to switch`" @click="emit('cycle-mode')">
          {{ mode.icon }} {{ mode.label }}
        </button>
        <button
          v-if="characterNames.length"
          class="ctx-chip"
          :title="`Characters in this chat: ${characterNames.join(', ')} — click to change`"
          @click="emit('show-sidebar')"
        >
          👤 <span class="ctx-names">{{ characterNames.join(', ') }}</span>
        </button>
        <span
          v-if="pinnedCount && mode.id !== 'text'"
          class="ctx-chip pins"
          :title="`${pinnedCount} pinned image${pinnedCount !== 1 ? 's' : ''}: sent as references with every new image`"
        >
          📌 {{ pinnedCount }}
          <button class="ctx-x" title="Unpin all" @click="emit('unpin-all')">✕</button>
        </span>
        <button
          v-if="refs"
          class="ctx-chip refs"
          :class="{ warn: leftOut.length, open: trayOpen }"
          :title="refsTitle"
          @click="trayOpen = !trayOpen"
        >
          {{ leftOut.length ? '⚠' : '🖼' }} {{ refs.sent }}{{ refs.max ? `/${refs.max}` : '' }}
        </button>
        <textarea
          ref="textarea"
          v-model="draft"
          rows="1"
          :placeholder="placeholder"
          @input="autosize"
          @keydown="onKeydown"
          @paste="onPaste"
        ></textarea>
        <button v-if="sending" class="send stop" title="Stop" @click="emit('stop')">■</button>
        <button v-else class="send" :disabled="!canSend" title="Send (Enter)" @click="trySend">↑</button>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* What goes with the message: attached characters, pinned images */
.ctx-chip {
  flex-shrink: 1;
  min-width: 0;
  max-width: 180px;
  height: 30px;
  margin-bottom: 3px;
  padding: 0 10px;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  border-radius: 999px;
  border: 1px solid var(--border);
  background: var(--surface);
  color: var(--text2);
  font-size: 0.75rem;
  white-space: nowrap;
  cursor: pointer;
}

.ctx-chip:hover {
  color: var(--text);
}

.ctx-chip.pins {
  flex-shrink: 0;
  cursor: default;
  padding-right: 4px;
}

.ctx-chip.refs {
  flex-shrink: 0;
}

.ctx-chip.open {
  border-color: var(--accent);
}

.ctx-chip.warn,
.ref-head .warn {
  color: var(--yellow);
}

.ctx-chip.warn {
  border-color: var(--yellow);
}

/* The next image's reference images */
.ref-tray {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 6px 4px 8px;
  border-bottom: 1px solid var(--border);
  margin-bottom: 4px;
}

.ref-head {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  font-size: 0.75rem;
  color: var(--text2);
  line-height: 1.4;
}

.ref-head > span {
  flex: 1;
}

.ref-link {
  border: none;
  background: none;
  color: var(--accent);
  font-size: 0.75rem;
  cursor: pointer;
  padding: 2px 4px;
}

.ref-group {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
}

.ref-label {
  width: 72px;
  font-size: 0.7rem;
  color: var(--text2);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.ref {
  position: relative;
  width: 44px;
  height: 44px;
  padding: 0;
  border-radius: 8px;
  border: 2px solid var(--accent);
  background: var(--surface);
  overflow: hidden;
  cursor: pointer;
}

.ref img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}

.ref.forced {
  border-color: var(--green);
}

.ref.dropped,
.ref.capped {
  border: 2px dashed var(--yellow);
}

.ref.dropped img,
.ref.capped img {
  opacity: 0.45;
}

.ref.off {
  border-color: var(--border);
}

.ref.off img {
  opacity: 0.2;
  filter: grayscale(1);
}

.ref-badge {
  position: absolute;
  right: 2px;
  bottom: 2px;
  min-width: 16px;
  height: 16px;
  padding: 0 3px;
  border-radius: 8px;
  background: rgba(0, 0, 0, 0.7);
  color: #fff;
  font-size: 0.6rem;
  line-height: 16px;
  text-align: center;
}

.ctx-names {
  overflow: hidden;
  text-overflow: ellipsis;
}

.ctx-x {
  width: 20px;
  height: 20px;
  border: none;
  border-radius: 50%;
  background: none;
  color: var(--text2);
  font-size: 0.65rem;
  cursor: pointer;
}

.ctx-x:hover {
  background: var(--surface2);
  color: var(--text);
}

@media (max-width: 600px) {
  .ctx-names {
    display: none;
  }
}

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
  transition:
    border-color 0.2s,
    box-shadow 0.2s;
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
  transition:
    opacity 0.2s,
    transform 0.15s;
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

@media (max-width: 860px) {
  .composer-wrap {
    padding: 0 8px 8px;
  }
}
</style>

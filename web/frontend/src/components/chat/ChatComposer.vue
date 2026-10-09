<script setup>
import { computed, nextTick, ref } from 'vue'
import { takeFiles } from '../../utils/files'

// The message box: attachments, what goes with the message (characters,
// pinned images), and one row of controls. v-model is the draft.
const draft = defineModel({ type: String, required: true })
const props = defineProps({
  mode: { type: Object, required: true }, // the current MODES entry
  attachments: { type: Array, required: true }, // from useChatAttachments
  characterNames: { type: Array, default: () => [] }, // attached characters in use
  pinnedCount: { type: Number, default: 0 },
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
])

const textarea = ref(null)

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
    emit('send')
  }
}

function onPaste(e) {
  const files = [...(e.clipboardData?.files || [])]
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

      <div v-if="characterNames.length" class="pinned-row">
        <span>👤 {{ characterNames.join(', ') }}</span>
        <button @click="emit('show-sidebar')">Change</button>
      </div>

      <div v-if="pinnedCount && mode.id !== 'text'" class="pinned-row">
        <span
          >📌 {{ pinnedCount }} image{{ pinnedCount !== 1 ? 's' : '' }} pinned: sent as references with every new
          image</span
        >
        <button @click="emit('unpin-all')">Unpin all</button>
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
        <button v-else class="send" :disabled="!canSend" title="Send (Enter)" @click="emit('send')">↑</button>
      </div>
    </div>
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

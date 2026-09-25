<script setup>
import { computed, ref, nextTick, onMounted, onBeforeUnmount } from 'vue'
import { marked } from 'marked'
import DOMPurify from 'dompurify'
import { chatMediaUrl } from '../../composables/useChat'

const props = defineProps({
  message: { type: Object, required: true },
  convId: { type: String, required: true },
  canRetry: { type: Boolean, default: false },
  canEdit: { type: Boolean, default: false },
  laterCount: { type: Number, default: 0 },   // messages an edit would remove
})
const emit = defineEmits(['retry', 'open-media', 'stop', 'edit', 'resend'])

marked.setOptions({ gfm: true, breaks: true })

const isUser = computed(() => props.message.role === 'user')
const streaming = computed(() => props.message.status === 'streaming')
const html = computed(() => {
  if (!props.message.content) return ''
  return DOMPurify.sanitize(marked.parse(props.message.content))
})
// Image/Video mode failures already show on the media card — don't repeat them
const errorShownOnMedia = computed(() =>
  props.message.media?.some(m => m.status === 'error' && m.error === props.message.error))
const shortModel = (id) => (id || '').split('/').pop()
const modelShort = computed(() => shortModel(props.message.model))
// Media-only replies (Image/Video mode) have no text model to name
const showTextModel = computed(() => !!props.message.content || !props.message.media?.length)

// Ticking clock for "rendering 1:23" on pending videos
const now = ref(Date.now())
let timer = null
onMounted(() => { timer = setInterval(() => { now.value = Date.now() }, 1000) })
onBeforeUnmount(() => clearInterval(timer))

function elapsed() {
  const start = Date.parse(props.message.created_at) || now.value
  const s = Math.max(0, Math.floor((now.value - start) / 1000))
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`
}

function url(item) {
  return chatMediaUrl(props.convId, item.file)
}

// ── Inline edit (user messages) ──
const editing = ref(false)
const editText = ref('')
const editBox = ref(null)

function startEdit() {
  editText.value = props.message.content || ''
  editing.value = true
  nextTick(() => {
    const el = editBox.value
    if (!el) return
    fitEditBox()
    el.focus({ preventScroll: true })
    el.setSelectionRange(el.value.length, el.value.length)
    el.closest('.msg')?.scrollIntoView({ block: 'nearest' })
  })
}

function fitEditBox() {
  const el = editBox.value
  if (!el) return
  el.style.height = 'auto'
  el.style.height = `${Math.min(el.scrollHeight, 320)}px`
}

function submitEdit() {
  const text = editText.value.trim()
  if (!text && !props.message.media?.length) return
  editing.value = false
  if (text !== (props.message.content || '').trim()) emit('edit', text)
}

function onEditKeydown(e) {
  if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) {
    e.preventDefault()
    submitEdit()
  }
  if (e.key === 'Escape') editing.value = false
}

const copied = ref(false)
async function copy() {
  try {
    await navigator.clipboard.writeText(props.message.content || '')
    copied.value = true
    setTimeout(() => { copied.value = false }, 1500)
  } catch { /* clipboard blocked (e.g. http) — ignore */ }
}

function fmtCost(c) {
  if (!c) return ''
  return c < 0.01 ? `$${c.toFixed(4)}` : `$${c.toFixed(2)}`
}
</script>

<template>
  <div class="msg" :class="isUser ? 'msg-user' : 'msg-assistant'">
    <div v-if="!isUser" class="avatar">✦</div>

    <div class="msg-body">
      <!-- User attachments sit above their text, like Gemini -->
      <div v-if="isUser && message.media?.length" class="attachments">
        <img
          v-for="item in message.media"
          :key="item.id"
          :src="url(item)"
          class="attachment-thumb"
          alt="attachment"
          @click="emit('open-media', { url: url(item), kind: 'image' })"
        />
      </div>

      <div v-if="isUser && editing" class="edit-box">
        <textarea
          ref="editBox"
          v-model="editText"
          rows="1"
          @input="fitEditBox"
          @keydown="onEditKeydown"
        ></textarea>
        <div class="edit-actions">
          <span v-if="laterCount" class="edit-note">
            Resends this prompt and replaces the {{ laterCount }} message{{ laterCount === 1 ? '' : 's' }} after it.
            Generated images/videos stay in the Library.
          </span>
          <button class="meta-btn" @click="editing = false">Cancel</button>
          <button class="edit-send" :disabled="!editText.trim() && !message.media?.length" @click="submitEdit">Send</button>
        </div>
      </div>
      <div v-else-if="isUser && message.content" class="bubble">{{ message.content }}</div>
      <div v-if="isUser && canEdit && !editing" class="user-actions">
        <button class="meta-btn" title="Edit and resend" @click="startEdit">✎ Edit</button>
        <button class="meta-btn" title="Resend this prompt for a different response" @click="emit('resend')">↻ Retry</button>
      </div>

      <template v-if="!isUser">
        <div v-if="html" class="markdown" v-html="html"></div>
        <div v-else-if="streaming && !message.media?.length" class="thinking">
          <span></span><span></span><span></span>
        </div>
        <span v-if="streaming && html" class="cursor"></span>

        <div v-if="message.media?.length" class="media-grid" :class="{ single: message.media.length === 1 }">
          <div v-for="item in message.media" :key="item.id" class="media-item" :class="item.kind">
            <template v-if="item.status === 'done' && item.file">
              <img
                v-if="item.kind === 'image'"
                :src="url(item)"
                :alt="item.prompt || 'generated image'"
                @click="emit('open-media', { url: url(item), kind: 'image', prompt: item.prompt })"
              />
              <video v-else :src="url(item)" controls loop playsinline preload="metadata"></video>
              <div class="media-overlay">
                <a :href="url(item)" :download="item.file" class="media-btn" title="Download" @click.stop>⤓</a>
              </div>
            </template>

            <div v-else-if="item.status === 'pending'" class="media-pending">
              <div class="shimmer"></div>
              <div class="pending-label">
                <div class="spinner"></div>
                <span v-if="item.kind === 'image'">Creating image…</span>
                <span v-else>Rendering video… {{ elapsed() }}</span>
              </div>
              <div v-if="item.prompt" class="pending-prompt">{{ item.prompt }}</div>
            </div>

            <div v-else class="media-error">
              <strong>{{ item.kind === 'image' ? 'Image' : 'Video' }} failed</strong>
              <span>{{ item.error || 'Unknown error' }}</span>
            </div>

            <!-- Which model made this — the footer only names the chat model -->
            <div v-if="item.model" class="media-caption" :title="item.model">
              {{ item.kind === 'image' ? '🖼' : '🎬' }} {{ shortModel(item.model) }}<template v-if="item.cost"> · {{ fmtCost(item.cost) }}</template>
            </div>
          </div>
        </div>

        <div v-if="message.status === 'error' && message.error && !errorShownOnMedia" class="msg-error">⚠ {{ message.error }}</div>

        <div class="msg-meta">
          <button v-if="streaming" class="meta-btn" @click="emit('stop')">■ Stop</button>
          <template v-else>
            <button v-if="message.content" class="meta-btn" @click="copy">{{ copied ? '✓ Copied' : '⧉ Copy' }}</button>
            <button v-if="canRetry" class="meta-btn" @click="emit('retry')">↻ Retry</button>
          </template>
          <span v-if="modelShort && showTextModel" class="meta-info" :title="message.model">💬 {{ modelShort }}</span>
          <span v-if="message.cost" class="meta-info" title="Total OpenRouter cost for this reply (text + media)">total {{ fmtCost(message.cost) }}</span>
        </div>
      </template>
    </div>
  </div>
</template>

<style scoped>
.msg {
  display: flex;
  gap: 12px;
  max-width: 820px;
  width: 100%;
  margin: 0 auto;
}

.msg-user {
  justify-content: flex-end;
}

.msg-user .msg-body {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  max-width: 80%;
}

.msg-assistant .msg-body {
  flex: 1;
  min-width: 0;
}

.avatar {
  flex-shrink: 0;
  width: 30px;
  height: 30px;
  border-radius: 50%;
  display: grid;
  place-items: center;
  background: linear-gradient(145deg, var(--accent), #4b8bf5);
  color: white;
  font-size: 0.9rem;
  margin-top: 2px;
}

.user-actions {
  display: flex;
  gap: 2px;
  opacity: 0;
  transition: opacity 0.15s;
  margin-top: 2px;
}

.msg-user:hover .user-actions,
.user-actions:focus-within {
  opacity: 1;
}

@media (hover: none) {
  .user-actions {
    opacity: 1;
  }
}

.edit-box {
  width: min(640px, 80vw);
  background: var(--surface2);
  border: 1px solid var(--accent);
  border-radius: 18px;
  padding: 10px 12px 8px;
}

.edit-box textarea {
  width: 100%;
  min-height: 24px;
  max-height: 320px;
  resize: none;
  border: none;
  background: transparent;
  padding: 2px;
  font-size: 0.95rem;
  line-height: 1.5;
}

.edit-actions {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 6px;
  margin-top: 6px;
}

.edit-note {
  flex: 1;
  font-size: 0.72rem;
  color: var(--text2);
  line-height: 1.35;
}

.edit-send {
  padding: 5px 14px;
  border-radius: 999px;
  border: none;
  background: linear-gradient(145deg, var(--accent), #5a4bd1);
  color: white;
  font-size: 0.8rem;
  font-weight: 600;
  cursor: pointer;
}

.edit-send:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.bubble {
  background: var(--surface2);
  border-radius: 18px 18px 4px 18px;
  padding: 10px 16px;
  white-space: pre-wrap;
  word-break: break-word;
  line-height: 1.5;
}

.attachments {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 6px;
  margin-bottom: 6px;
}

.attachment-thumb {
  width: 120px;
  height: 120px;
  object-fit: cover;
  border-radius: 12px;
  cursor: zoom-in;
  border: 1px solid var(--border);
}

/* ── Markdown ─────────────────────────── */
.markdown {
  line-height: 1.65;
  word-break: break-word;
  display: inline;
}

.markdown :deep(> *:first-child) { margin-top: 0; }
.markdown :deep(p) { margin: 0 0 0.8em; }
.markdown :deep(h1), .markdown :deep(h2), .markdown :deep(h3) { margin: 1em 0 0.5em; line-height: 1.3; }
.markdown :deep(h1) { font-size: 1.35rem; }
.markdown :deep(h2) { font-size: 1.2rem; }
.markdown :deep(h3) { font-size: 1.05rem; }
.markdown :deep(ul), .markdown :deep(ol) { margin: 0 0 0.8em 1.4em; }
.markdown :deep(li) { margin: 0.2em 0; }
.markdown :deep(a) { color: var(--accent2); }
.markdown :deep(blockquote) {
  border-left: 3px solid var(--border);
  padding-left: 12px;
  color: var(--text2);
  margin: 0 0 0.8em;
}
.markdown :deep(code) {
  font-family: 'SFMono-Regular', Consolas, monospace;
  font-size: 0.85em;
  background: var(--surface2);
  padding: 1px 5px;
  border-radius: 4px;
}
.markdown :deep(pre) {
  background: #141418;
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 12px 14px;
  overflow-x: auto;
  margin: 0 0 0.8em;
}
.markdown :deep(pre code) { background: none; padding: 0; font-size: 0.82rem; }
.markdown :deep(table) { border-collapse: collapse; margin: 0 0 0.8em; display: block; overflow-x: auto; }
.markdown :deep(th), .markdown :deep(td) { border: 1px solid var(--border); padding: 5px 10px; }
.markdown :deep(th) { background: var(--surface2); }
.markdown :deep(hr) { border: none; border-top: 1px solid var(--border); margin: 1em 0; }

.cursor {
  display: inline-block;
  width: 8px;
  height: 1em;
  background: var(--accent2);
  vertical-align: text-bottom;
  animation: pulse 1s ease-in-out infinite;
  margin-left: 2px;
}

.thinking {
  display: flex;
  gap: 5px;
  padding: 10px 0;
}

.thinking span {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--text2);
  animation: pulse 1.2s ease-in-out infinite;
}

.thinking span:nth-child(2) { animation-delay: 0.2s; }
.thinking span:nth-child(3) { animation-delay: 0.4s; }

/* ── Media ────────────────────────────── */
.media-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
  gap: 10px;
  margin: 8px 0 4px;
}

.media-grid.single {
  grid-template-columns: minmax(0, 520px);
}

.media-item {
  position: relative;
  border-radius: 14px;
  overflow: hidden;
  background: var(--surface);
  border: 1px solid var(--border);
}

.media-item img,
.media-item video {
  display: block;
  width: 100%;
  height: auto;
  max-height: 560px;
  object-fit: contain;
  background: #000;
}

.media-item img {
  cursor: zoom-in;
}

.media-overlay {
  position: absolute;
  top: 8px;
  right: 8px;
  opacity: 0;
  transition: opacity 0.2s;
}

.media-item:hover .media-overlay {
  opacity: 1;
}

.media-btn {
  display: grid;
  place-items: center;
  width: 32px;
  height: 32px;
  border-radius: 8px;
  background: rgba(0, 0, 0, 0.65);
  color: white;
  text-decoration: none;
  font-size: 1rem;
}

.media-caption {
  padding: 6px 10px;
  font-size: 0.72rem;
  color: var(--text2);
  border-top: 1px solid var(--border);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.media-pending {
  position: relative;
  aspect-ratio: 16 / 10;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 10px;
  padding: 16px;
  overflow: hidden;
}

.media-item.image .media-pending {
  aspect-ratio: 1;
}

.shimmer {
  position: absolute;
  inset: 0;
  background: linear-gradient(110deg, transparent 30%, rgba(108, 92, 231, 0.12) 50%, transparent 70%);
  background-size: 200% 100%;
  animation: shimmer 1.8s linear infinite;
}

@keyframes shimmer {
  from { background-position: 200% 0; }
  to { background-position: -200% 0; }
}

.pending-label {
  position: relative;
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 0.85rem;
}

.pending-prompt {
  position: relative;
  font-size: 0.75rem;
  color: var(--text2);
  text-align: center;
  max-width: 90%;
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.media-error {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 14px;
  font-size: 0.82rem;
  color: var(--red);
  background: rgba(225, 112, 85, 0.08);
}

.media-error span {
  color: var(--text2);
  word-break: break-word;
}

.msg-error {
  margin-top: 6px;
  padding: 8px 12px;
  border-radius: 8px;
  font-size: 0.85rem;
  color: var(--red);
  background: rgba(225, 112, 85, 0.08);
  border: 1px solid rgba(225, 112, 85, 0.25);
  word-break: break-word;
}

.msg-meta {
  display: flex;
  align-items: center;
  gap: 4px;
  margin-top: 6px;
  min-height: 24px;
}

.meta-btn {
  background: none;
  border: none;
  color: var(--text2);
  font-size: 0.75rem;
  padding: 3px 7px;
  border-radius: 6px;
  cursor: pointer;
}

.meta-btn:hover {
  background: var(--surface2);
  color: var(--text);
}

.meta-info {
  font-size: 0.72rem;
  color: var(--text2);
  padding: 0 6px;
  opacity: 0.7;
}
</style>

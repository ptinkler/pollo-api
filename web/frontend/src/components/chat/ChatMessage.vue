<script setup>
import { computed, ref, nextTick, inject, onMounted, onBeforeUnmount } from 'vue'
import { marked } from 'marked'
import DOMPurify from 'dompurify'
import { chatMediaUrl } from '../../composables/useChat'
import { useCopy } from '../../composables/useClipboard'
import { shortModel, fmtCost } from '../../utils/format'
import ModelPicker from './ModelPicker.vue'
import ForkList from './ForkList.vue'

const props = defineProps({
  message: { type: Object, required: true },
  convId: { type: String, required: true },
  canRetry: { type: Boolean, default: false },
  canEdit: { type: Boolean, default: false },
  canSwitch: { type: Boolean, default: false }, // ‹ › arrows usable (not mid-reply)
  canBranch: { type: Boolean, default: false }, // ⑂ Branch on a reply (prompts go with canEdit)
})
const emit = defineEmits([
  'retry',
  'open-media',
  'stop',
  'edit',
  'resend',
  'regenerate',
  'branch',
  'use-image',
  'use-text',
  'pin',
  'delete',
  'fork',
  'open-chat',
])

// Model catalogues, provided by ChatView, for "Try another model"
const chatModels = inject('chatModels', { image: [], video: [] })

marked.setOptions({ gfm: true, breaks: true })

const isUser = computed(() => props.message.role === 'user')
const streaming = computed(() => props.message.status === 'streaming')
// Models sometimes echo a "[generated image: <prompt>]" line in their reply
// (older chat history recorded media that way). The image itself is shown
// below, so hide those lines — display only; the stored reply is untouched.
const MEDIA_NOTE_LINE =
  /^[ \t]*\[(?:generated (?:image|video)|(?:image|video) (?:rendering|failed))\b[^\n]*\][ \t]*$/gim
const displayText = computed(() =>
  (props.message.content || '')
    .replace(MEDIA_NOTE_LINE, '')
    .replace(/\n{3,}/g, '\n\n')
    .trim(),
)
const html = computed(() => {
  if (!displayText.value) return ''
  return DOMPurify.sanitize(marked.parse(displayText.value))
})
// Image/Video mode failures already show on the media card — don't repeat them
const errorShownOnMedia = computed(() =>
  props.message.media?.some(m => m.status === 'error' && m.error === props.message.error),
)
const modelShort = computed(() => shortModel(props.message.model))
// Media-only replies (Image/Video mode) have no text model to name
const showTextModel = computed(() => !!props.message.content || !props.message.media?.length)

// Ticking clock for "rendering 1:23" on pending videos
const now = ref(Date.now())
let timer = null
onMounted(() => {
  timer = setInterval(() => {
    now.value = Date.now()
  }, 1000)
})
onBeforeUnmount(() => clearInterval(timer))

function elapsed() {
  const start = Date.parse(props.message.created_at) || now.value
  const s = Math.max(0, Math.floor((now.value - start) / 1000))
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`
}

// The settings a generated item was made with. For Pollo these are what was
// actually sent (defaults included); for OpenRouter only what we asked for —
// the provider fills in the rest without saying.
function specs(item) {
  const p = item.params || {}
  const isVideo = item.kind === 'video'
  return [
    ...(isVideo ? videoSource(p) : []),
    isVideo && p.duration && `${p.duration}s`,
    p.resolution,
    p.aspect_ratio,
    isVideo && p.generate_audio != null && (p.generate_audio ? 'audio' : 'no audio'),
    p.character_names?.length && `👤 ${p.character_names.join(', ')}`,
  ].filter(Boolean)
}

// What a video was made from, besides its prompt
function videoSource(p) {
  const frames = p.last_frame ? 'first+last frame' : p.first_frame && !p.refs?.length && 'from image'
  return [p.source_video && 'from video', frames]
}

// "4 refs", or "2 of 4 refs" when the model took fewer than were picked
// (Venice edit models cap the count; the first ones win)
function refsLabel(p) {
  const n = p.refs.length
  const used = p.refs_used
  return used != null && used < n ? `${used} of ${n} refs` : `${n} ref${n === 1 ? '' : 's'}`
}
function refsTitle(p) {
  const used = p.refs_used
  const list = p.refs.join(', ')
  return used != null && used < p.refs.length
    ? `The model takes ${used} image${used === 1 ? '' : 's'}, so only the first ${used} of these were sent: ${list}`
    : `Based on earlier image(s): ${list}`
}

function url(item) {
  return chatMediaUrl(props.convId, item.file)
}

// Prompts sent outside Auto mode say so — an edit or retry reruns them in that mode
const MODE_TAGS = { image: '🖼 Image', video: '🎬 Video', text: '💬 Text only' }
const modeTag = computed(() => MODE_TAGS[props.message.mode] || '')

// "Picture / video from this": hand an image, or this reply's text, to the
// composer in Image/Video mode. A selection inside the reply narrows the text.
const replyEl = ref(null)
function replyText() {
  const sel = window.getSelection?.()
  const picked = sel && !sel.isCollapsed && replyEl.value?.contains(sel.anchorNode) ? sel.toString().trim() : ''
  return picked || displayText.value
}
// Only saved images (not a reply still streaming) can be pinned as references
const canPin = item => item.kind === 'image' && !!item.file && typeof props.message.id === 'number'
const pinTitle = item =>
  item.pinned
    ? 'Pinned: sent as a reference with every new image. Click to unpin'
    : 'Pin as a reference: send it with every new image in this chat'

const useText = mode => emit('use-text', { text: replyText(), mode })

// ── Branches: other versions of this turn (from edits/retries) ──
const siblings = computed(() => props.message.siblings || [])
const branchIndex = computed(() => siblings.value.indexOf(props.message.id))
function goBranch(step) {
  const id = siblings.value[branchIndex.value + step]
  if (id != null) emit('branch', id)
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

const { copiedKey, copy } = useCopy()
</script>

<template>
  <div class="msg" :class="isUser ? 'msg-user' : 'msg-assistant'">
    <div v-if="!isUser" class="avatar">✦</div>

    <div class="msg-body">
      <!-- User attachments sit above their text, like Gemini -->
      <div v-if="isUser && message.media?.length" class="attachments">
        <div v-for="item in message.media" :key="item.id" class="attachment">
          <button
            v-if="canPin(item)"
            :class="['pin-btn', { on: item.pinned }]"
            :title="pinTitle(item)"
            :aria-pressed="!!item.pinned"
            @click.stop="emit('pin', { mediaId: item.id, pinned: !item.pinned })"
          >
            📌
          </button>
          <img
            :src="url(item)"
            class="attachment-thumb"
            alt="attachment"
            @click="emit('open-media', { url: url(item), kind: 'image', file: item.file })"
          />
          <span class="use-btns">
            <button
              title="New picture from this image (attaches it to your next message)"
              @click="emit('use-image', { file: item.file, mode: 'image' })"
            >
              🖼
            </button>
            <button
              title="Animate this image into a video (attaches it to your next message)"
              @click="emit('use-image', { file: item.file, mode: 'video' })"
            >
              🎬
            </button>
          </span>
        </div>
      </div>

      <div v-if="isUser && editing" class="edit-box">
        <textarea ref="editBox" v-model="editText" rows="1" @input="fitEditBox" @keydown="onEditKeydown"></textarea>
        <div class="edit-actions">
          <span class="edit-note">Sends as a new branch — the original stays available with the ‹ › arrows.</span>
          <button class="meta-btn" @click="editing = false">Cancel</button>
          <button class="edit-send" :disabled="!editText.trim() && !message.media?.length" @click="submitEdit">
            Send
          </button>
        </div>
      </div>
      <div v-else-if="isUser && message.content" class="bubble">{{ message.content }}</div>
      <div
        v-if="
          isUser && !editing && (canEdit || message.content || siblings.length > 1 || modeTag || message.forks?.length)
        "
        class="user-actions"
      >
        <ForkList
          v-if="message.forks?.length"
          :forks="message.forks"
          align="right"
          @open="id => emit('open-chat', id)"
        />
        <span
          v-if="modeTag"
          class="mode-tag"
          :title="`Last run in ${modeTag} mode — retrying or editing uses the mode selected now`"
          >{{ modeTag }}</span
        >
        <span v-if="siblings.length > 1" class="branch-nav">
          <button
            class="meta-btn"
            :disabled="!canSwitch || branchIndex <= 0"
            title="Previous version"
            @click="goBranch(-1)"
          >
            ‹
          </button>
          <span>{{ branchIndex + 1 }}/{{ siblings.length }}</span>
          <button
            class="meta-btn"
            :disabled="!canSwitch || branchIndex >= siblings.length - 1"
            title="Next version"
            @click="goBranch(1)"
          >
            ›
          </button>
        </span>
        <button v-if="message.content" class="meta-btn" title="Copy prompt" @click="copy(message.content, 'prompt')">
          {{ copiedKey === 'prompt' ? '✓' : '⧉' }}
        </button>
        <template v-if="canEdit">
          <button class="meta-btn" title="Edit and resend" @click="startEdit">✎</button>
          <button class="meta-btn" title="Resend this prompt for a different response" @click="emit('resend')">
            ↻
          </button>
          <button
            class="meta-btn"
            title="Start a new chat from here: everything up to this prompt and its reply, nothing after"
            @click="emit('fork')"
          >
            ⑂
          </button>
          <button
            class="meta-btn"
            title="Delete this prompt and its reply from the chat (images and videos stay in Media)"
            @click="emit('delete')"
          >
            🗑
          </button>
        </template>
      </div>

      <template v-if="!isUser">
        <!-- eslint-disable-next-line vue/no-v-html -- sanitised with DOMPurify (see `html`) -->
        <div v-if="html" ref="replyEl" class="markdown" v-html="html"></div>
        <div v-else-if="streaming && !message.media?.length" class="thinking">
          <span></span><span></span><span></span>
        </div>
        <span v-if="streaming && html" class="cursor"></span>

        <div v-if="message.media?.length" class="media-grid" :class="{ single: message.media.length === 1 }">
          <div
            v-for="item in message.media"
            :key="item.id"
            class="media-item"
            :class="[item.kind, { failed: item.status === 'error' }]"
          >
            <template v-if="item.status === 'done' && item.file">
              <img
                v-if="item.kind === 'image'"
                :src="url(item)"
                :alt="item.prompt || 'generated image'"
                @click="emit('open-media', { url: url(item), kind: 'image', prompt: item.prompt, file: item.file })"
              />
              <video v-else :src="url(item)" controls loop playsinline preload="metadata"></video>
              <button
                v-if="canPin(item)"
                :class="['pin-btn', { on: item.pinned }]"
                :title="pinTitle(item)"
                :aria-pressed="!!item.pinned"
                @click.stop="emit('pin', { mediaId: item.id, pinned: !item.pinned })"
              >
                📌
              </button>
              <div class="media-overlay">
                <template v-if="item.kind === 'image'">
                  <button
                    class="media-btn"
                    title="New picture from this image (attaches it to your next message)"
                    @click.stop="emit('use-image', { file: item.file, mode: 'image' })"
                  >
                    🖼
                  </button>
                  <button
                    class="media-btn"
                    title="Animate this image into a video (attaches it to your next message)"
                    @click.stop="emit('use-image', { file: item.file, mode: 'video' })"
                  >
                    🎬
                  </button>
                </template>
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
              <div v-if="specs(item).length" class="pending-specs">{{ specs(item).join(' · ') }}</div>
              <div v-if="item.prompt" class="pending-prompt" :title="item.prompt">{{ item.prompt }}</div>
            </div>

            <div v-else class="media-error">
              <strong>
                {{ item.kind === 'image' ? 'Image' : 'Video' }}
                {{ item.moderated ? 'blocked by moderation' : 'failed' }}
              </strong>
              <span>{{ item.error || 'Unknown error' }}</span>
              <!-- Nothing retries automatically — the user picks -->
              <div
                v-if="item.source === 'generated' && item.prompt && message.status !== 'streaming'"
                class="error-actions"
              >
                <button
                  class="retry-btn"
                  title="Run the same prompt on the same model again"
                  @click="emit('regenerate', { mediaId: item.id, model: null })"
                >
                  ↻ Retry
                </button>
                <ModelPicker
                  :model-value="''"
                  :models="chatModels[item.kind] || []"
                  :kind="item.kind"
                  :label="item.kind === 'image' ? 'Image' : 'Video'"
                  :allow-none="false"
                  trigger-text="Try another model…"
                  @update:model-value="model => model && emit('regenerate', { mediaId: item.id, model })"
                />
              </div>
            </div>

            <!-- Which model made this — the footer only names the chat model -->
            <div v-if="item.model || item.prompt" class="media-caption">
              <span class="caption-text" :title="[item.model, ...specs(item)].join(' · ')">
                {{ item.kind === 'image' ? '🖼' : '🎬' }} {{ shortModel(item.model)
                }}<template v-if="specs(item).length">
                  · <span class="caption-specs">{{ specs(item).join(' · ') }}</span></template
                ><template v-if="item.cost"> · {{ fmtCost(item.cost) }}</template
                ><template v-if="item.credits">
                  ·
                  <span title="Billed to your Pollo account"
                    >{{ item.credits }} credit{{ item.credits === 1 ? '' : 's' }}</span
                  ></template
                ><template v-if="item.params?.context">
                  · <span title="The image model was given the conversation">💬 context</span></template
                ><template v-if="item.params?.refs?.length">
                  · <span :title="refsTitle(item.params)">🔗 {{ refsLabel(item.params) }}</span></template
                >
              </span>
              <button
                v-if="item.prompt"
                class="caption-btn"
                :title="`Copy the prompt sent to the ${item.kind} model:\n${item.prompt}`"
                @click="copy(item.prompt, item.id)"
              >
                {{ copiedKey === item.id ? '✓ Copied' : '⧉ Prompt' }}
              </button>
            </div>
          </div>
        </div>

        <div v-if="message.status === 'error' && message.error && !errorShownOnMedia" class="msg-error">
          ⚠ {{ message.error }}
        </div>

        <div class="msg-meta">
          <span v-if="siblings.length > 1" class="branch-nav">
            <button
              class="meta-btn"
              :disabled="!canSwitch || branchIndex <= 0"
              title="Previous version"
              @click="goBranch(-1)"
            >
              ‹
            </button>
            <span>{{ branchIndex + 1 }}/{{ siblings.length }}</span>
            <button
              class="meta-btn"
              :disabled="!canSwitch || branchIndex >= siblings.length - 1"
              title="Next version"
              @click="goBranch(1)"
            >
              ›
            </button>
          </span>
          <button v-if="streaming" class="meta-btn" @click="emit('stop')">■ Stop</button>
          <template v-else>
            <button v-if="displayText" class="meta-btn" title="Copy reply" @click="copy(displayText, 'reply')">
              {{ copiedKey === 'reply' ? '✓' : '⧉' }}
            </button>
            <!-- mousedown.prevent keeps a selection in the reply alive for the click -->
            <!-- These reuse the reply's words; the buttons on an image reuse the image -->
            <button
              v-if="displayText"
              class="meta-btn"
              title="Put this reply's text (or the part you've selected) in the message box as an Image-mode prompt"
              @mousedown.prevent
              @click="useText('image')"
            >
              ✎🖼
            </button>
            <button
              v-if="displayText"
              class="meta-btn"
              title="Put this reply's text (or the part you've selected) in the message box as a Video-mode prompt"
              @mousedown.prevent
              @click="useText('video')"
            >
              ✎🎬
            </button>
            <button
              v-if="canRetry"
              class="meta-btn"
              title="Retry: another version of this reply"
              @click="emit('retry')"
            >
              ↻
            </button>
            <button
              v-if="canBranch"
              class="meta-btn"
              title="Start a new chat from here: everything up to this reply, nothing after"
              @click="emit('fork')"
            >
              ⑂
            </button>
          </template>
          <ForkList v-if="message.forks?.length" :forks="message.forks" @open="id => emit('open-chat', id)" />
          <span class="meta-spacer"></span>
          <span v-if="modelShort && showTextModel" class="meta-info model" :title="message.model"
            >💬 {{ modelShort }}</span
          >
          <span v-if="message.cost" class="meta-info" title="Total OpenRouter cost for this reply (text + media)"
            >total {{ fmtCost(message.cost) }}</span
          >
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
  align-items: center;
  gap: 2px;
  margin-top: 2px;
}

/* Action buttons fade in on hover; the branch arrows always show */
.user-actions > .meta-btn {
  opacity: 0;
  transition: opacity 0.15s;
}

.msg-user:hover .user-actions > .meta-btn,
.user-actions:focus-within > .meta-btn {
  opacity: 1;
}

@media (hover: none) {
  .user-actions > .meta-btn {
    opacity: 1;
  }
}

.mode-tag {
  font-size: 0.7rem;
  color: var(--text2);
  padding: 0 6px;
}

.branch-nav {
  display: inline-flex;
  align-items: center;
  font-size: 0.75rem;
  color: var(--text2);
  font-variant-numeric: tabular-nums;
}

.branch-nav .meta-btn {
  padding: 3px 6px;
  font-size: 0.9rem;
  line-height: 1;
}

.branch-nav .meta-btn:disabled {
  opacity: 0.35;
  cursor: default;
  background: none;
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

.attachment {
  position: relative;
}

/* Pin as reference: top-left, shown on hover, always shown once pinned */
.pin-btn {
  position: absolute;
  top: 6px;
  left: 6px;
  z-index: 1;
  width: 28px;
  height: 28px;
  border: none;
  border-radius: 8px;
  background: rgba(0, 0, 0, 0.65);
  font-size: 0.85rem;
  cursor: pointer;
  opacity: 0;
  filter: grayscale(1);
  transition: opacity 0.15s;
}

.attachment:hover .pin-btn,
.media-item:hover .pin-btn,
.pin-btn:focus-visible,
.pin-btn.on {
  opacity: 1;
}

.pin-btn.on {
  filter: none;
  background: var(--accent);
}

@media (hover: none) {
  .pin-btn {
    opacity: 1;
  }
}

.use-btns {
  position: absolute;
  top: 6px;
  right: 6px;
  display: flex;
  gap: 4px;
  opacity: 0;
  transition: opacity 0.15s;
}

.use-btns button {
  width: 28px;
  height: 28px;
  border: none;
  border-radius: 8px;
  background: rgba(0, 0, 0, 0.65);
  font-size: 0.85rem;
  cursor: pointer;
}

.attachment:hover .use-btns,
.use-btns:focus-within {
  opacity: 1;
}

@media (hover: none) {
  .use-btns {
    opacity: 1;
  }
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

.markdown :deep(> *:first-child) {
  margin-top: 0;
}
.markdown :deep(p) {
  margin: 0 0 0.8em;
}
.markdown :deep(h1),
.markdown :deep(h2),
.markdown :deep(h3) {
  margin: 1em 0 0.5em;
  line-height: 1.3;
}
.markdown :deep(h1) {
  font-size: 1.35rem;
}
.markdown :deep(h2) {
  font-size: 1.2rem;
}
.markdown :deep(h3) {
  font-size: 1.05rem;
}
.markdown :deep(ul),
.markdown :deep(ol) {
  margin: 0 0 0.8em 1.4em;
}
.markdown :deep(li) {
  margin: 0.2em 0;
}
.markdown :deep(a) {
  color: var(--accent2);
}
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
.markdown :deep(pre code) {
  background: none;
  padding: 0;
  font-size: 0.82rem;
}
.markdown :deep(table) {
  border-collapse: collapse;
  margin: 0 0 0.8em;
  display: block;
  overflow-x: auto;
}
.markdown :deep(th),
.markdown :deep(td) {
  border: 1px solid var(--border);
  padding: 5px 10px;
}
.markdown :deep(th) {
  background: var(--surface2);
}
.markdown :deep(hr) {
  border: none;
  border-top: 1px solid var(--border);
  margin: 1em 0;
}

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

.thinking span:nth-child(2) {
  animation-delay: 0.2s;
}
.thinking span:nth-child(3) {
  animation-delay: 0.4s;
}

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

.media-overlay {
  display: flex;
  gap: 6px;
}

.media-btn {
  border: none;
  cursor: pointer;
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
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 6px 4px 10px;
  font-size: 0.72rem;
  color: var(--text2);
  border-top: 1px solid var(--border);
}

.caption-text {
  flex: 1;
  min-width: 0;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.caption-btn {
  flex-shrink: 0;
  background: none;
  border: none;
  color: var(--text2);
  font-size: 0.72rem;
  padding: 3px 7px;
  border-radius: 6px;
  cursor: pointer;
}

.caption-btn:hover {
  background: var(--surface2);
  color: var(--text);
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
  from {
    background-position: 200% 0;
  }
  to {
    background-position: -200% 0;
  }
}

.pending-label {
  position: relative;
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 0.85rem;
}

.pending-specs {
  position: relative;
  font-size: 0.75rem;
  color: var(--accent2);
}

.caption-specs {
  color: var(--text);
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

/* Failed cards host the model-picker popup, so they mustn't clip it */
.media-item.failed {
  overflow: visible;
}

.media-item.failed .media-error {
  border-radius: 14px 14px 0 0;
}

.error-actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  margin-top: 8px;
}

.retry-btn {
  background: linear-gradient(145deg, var(--accent), #5a4bd1);
  border: none;
  border-radius: 8px;
  padding: 5px 12px;
  color: white;
  font-size: 0.78rem;
  font-weight: 600;
  cursor: pointer;
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
  flex-wrap: wrap;
  align-items: center;
  gap: 2px 4px;
  margin-top: 6px;
  min-height: 24px;
}

.meta-btn {
  background: none;
  border: none;
  color: var(--text2);
  font-size: 0.8rem;
  line-height: 1.2;
  white-space: nowrap;
  min-width: 26px;
  padding: 3px 6px;
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
  white-space: nowrap;
}

/* Model and cost sit at the right end; a long model name is cut short */
.meta-spacer {
  flex: 1;
}

.meta-info.model {
  max-width: 220px;
  overflow: hidden;
  text-overflow: ellipsis;
}
</style>

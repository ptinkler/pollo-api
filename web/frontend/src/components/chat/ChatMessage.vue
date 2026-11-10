<script setup>
import { computed, reactive, ref, nextTick, inject, onMounted, onBeforeUnmount } from 'vue'
import { marked } from 'marked'
import DOMPurify from 'dompurify'
import { chatMediaPreviewUrl, chatMediaUrl } from '../../composables/useChat'
import { characterImageUrl } from '../../composables/useCharacters'
import { useCopy } from '../../composables/useClipboard'
import { shortModel, fmtCost } from '../../utils/format'
import ModelPicker from './ModelPicker.vue'
import ForkList from './ForkList.vue'
import RequestDialog from './RequestDialog.vue'

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
  'reword',
  'pin',
  'delete',
  'fork',
  'open-chat',
])

// Model catalogues, provided by ChatView, for "Try another model"
const KIND_LABEL = { image: 'Image', video: 'Video', audio: 'Audio' }
const KIND_ICON = { image: '🖼', video: '🎬', audio: '🔊' }
const chatModels = inject('chatModels', { image: [], video: [], audio: [] })

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
  return used != null && used < p.refs.length
    ? `The model takes ${used} image${used === 1 ? '' : 's'}, so only the first ${used} of these were sent:`
    : 'Based on these images:'
}
// A ref is a chat file or a character image ("char:<id>/<file>")
function refUrl(r) {
  const m = /^char:(\d+)\/(.+)$/.exec(r)
  return m ? characterImageUrl(m[1], m[2]) : chatMediaUrl(props.convId, r)
}

// Hovering "🔗 4 refs" shows the reference images. Teleported and fixed so
// the caption's overflow clipping doesn't cut it off.
const refsPeek = ref(null) // { params, x, y }
function showRefs(e, params) {
  const r = e.currentTarget.getBoundingClientRect()
  refsPeek.value = { params, x: r.left, y: r.top }
}

function url(item) {
  return chatMediaUrl(props.convId, item.file)
}

// What's shown in the chat: a scaled-down copy (a big chat's full images add up)
function preview(item) {
  return chatMediaPreviewUrl(props.convId, item.file)
}

// Prompts sent outside Auto mode say so — an edit or retry reruns them in that mode
const MODE_TAGS = { image: '🖼 Image', video: '🎬 Video', text: '💬 Text only' }
const modeTag = computed(() => MODE_TAGS[props.message.mode] || '')

const replyEl = ref(null)
// Only saved images (not a reply still streaming) can be pinned as references
const canPin = item => item.kind === 'image' && !!item.file && typeof props.message.id === 'number'
const pinTitle = item =>
  item.pinned
    ? 'Pinned: sent as a reference with every new image. Click to unpin'
    : 'Pin as a reference: send it with every new image in this chat'

const vFocusSelect = { mounted: el => (el.focus(), el.select()) }

// Can this picture/clip be made again? (ours, finished, and the reply is idle)
// What the big view (GenerationModal) needs: everything the card knows, plus
// where it lives, so its actions can act on the right message.
const bigView = item => ({
  ...shownItem(item),
  url: url(shownItem(item)),
  message_id: props.message.id,
  conversation_id: props.convId,
})

const canRemake = item =>
  item.status === 'done' && item.source === 'generated' && !!item.prompt && props.message.status !== 'streaming'

// Earlier pictures this card has shown, oldest first; the live one is last.
// The arrows only change what you are looking at — the newest stays the real one.
const versionsOf = item => item.versions || []
const shownIndex = reactive({})
const versionAt = item => shownIndex[item.id] ?? versionsOf(item).length
const shownItem = item => {
  const i = versionAt(item)
  return i < versionsOf(item).length ? { ...item, ...versionsOf(item)[i] } : item
}
const stepVersion = (item, by) => {
  const next = versionAt(item) + by
  if (next >= 0 && next <= versionsOf(item).length) shownIndex[item.id] = next
}

// The box the pencil and Redo open: one prompt, applied to this picture alone.
// `edit` sends the picture back as the reference; Redo just re-runs the words.
const promptBox = ref(null)
const openPrompt = (item, edit) => (promptBox.value = { mediaId: item.id, edit, text: edit ? '' : item.prompt || '' })
function submitPrompt(item) {
  const box = promptBox.value
  if (!box?.text.trim()) return
  promptBox.value = null
  delete shownIndex[item.id] // show the new picture, not whatever version was open
  emit('regenerate', {
    mediaId: item.id,
    model: item.model || null,
    prompt: box.text.trim(),
    edit: box.edit,
    replace: true,
  })
}

// Branches: other versions of this turn (from edits/retries)
const siblings = computed(() => props.message.siblings || [])
const branchIndex = computed(() => siblings.value.indexOf(props.message.id))
function goBranch(step) {
  const id = siblings.value[branchIndex.value + step]
  if (id != null) emit('branch', id)
}

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
// The media item whose provider request and response are open (RequestDialog)
const requestItem = ref(null)
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
            <svg class="ic sm"><use href="#s-pin" /></svg>
          </button>
          <audio v-if="item.kind === 'audio'" :src="url(item)" class="attachment-audio" controls></audio>
          <img
            v-else
            :src="preview(item)"
            class="attachment-thumb"
            alt="attachment"
            loading="lazy"
            decoding="async"
            @click="emit('open-media', bigView(item))"
          />
          <span v-if="item.kind !== 'audio'" class="use-btns">
            <button
              title="Attach this picture and switch to Image mode"
              @click="emit('use-image', { file: item.file, mode: 'image' })"
            >
              <svg class="ic sm"><use href="#s-image" /></svg>
            </button>
            <button
              title="Attach this picture and switch to Video mode"
              @click="emit('use-image', { file: item.file, mode: 'video' })"
            >
              <svg class="ic sm"><use href="#s-film" /></svg>
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
                :src="preview(shownItem(item))"
                :alt="item.prompt || 'generated image'"
                loading="lazy"
                decoding="async"
                @click="emit('open-media', bigView(item))"
              />
              <div v-if="versionsOf(item).length" class="ver-nav" @click.stop>
                <button :disabled="versionAt(item) === 0" title="Earlier version" @click="stepVersion(item, -1)">
                  ‹
                </button>
                <span :title="versionAt(item) < versionsOf(item).length ? shownItem(item).prompt : 'Latest'">
                  {{ versionAt(item) + 1 }}/{{ versionsOf(item).length + 1 }}
                </span>
                <button
                  :disabled="versionAt(item) === versionsOf(item).length"
                  title="Later version"
                  @click="stepVersion(item, 1)"
                >
                  ›
                </button>
              </div>
              <audio v-else-if="item.kind === 'audio'" :src="url(item)" class="media-audio" controls></audio>
              <video v-else :src="url(item)" controls loop playsinline preload="metadata"></video>
              <button
                v-if="canPin(item)"
                :class="['pin-btn', { on: item.pinned }]"
                :title="pinTitle(item)"
                :aria-pressed="!!item.pinned"
                @click.stop="emit('pin', { mediaId: item.id, pinned: !item.pinned })"
              >
                <svg class="ic sm"><use href="#s-pin" /></svg>
              </button>
              <div class="media-overlay">
                <template v-if="item.kind === 'image'">
                  <button
                    class="media-btn"
                    title="Attach this picture and switch to Image mode"
                    @click.stop="emit('use-image', { file: item.file, mode: 'image' })"
                  >
                    <svg class="ic"><use href="#s-image" /></svg>
                  </button>
                  <button
                    class="media-btn"
                    title="Attach this picture and switch to Video mode"
                    @click.stop="emit('use-image', { file: item.file, mode: 'video' })"
                  >
                    <svg class="ic"><use href="#s-film" /></svg>
                  </button>
                </template>
                <a :href="url(item)" :download="item.file" class="media-btn" title="Download" @click.stop>
                  <svg class="ic"><use href="#s-download" /></svg>
                </a>
              </div>
            </template>

            <div v-else-if="item.status === 'pending'" class="media-pending">
              <div class="shimmer"></div>
              <div class="pending-label">
                <div class="spinner"></div>
                <span v-if="item.kind === 'image'">Creating image…</span>
                <span v-else-if="item.kind === 'audio'">Composing audio… {{ elapsed() }}</span>
                <span v-else>Rendering video… {{ elapsed() }}</span>
              </div>
              <div v-if="specs(item).length" class="pending-specs">{{ specs(item).join(' · ') }}</div>
              <div v-if="item.prompt" class="pending-prompt" :title="item.prompt">{{ item.prompt }}</div>
            </div>

            <div v-else class="media-error">
              <strong>
                {{ KIND_LABEL[item.kind] || 'Video' }}
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
                  title="Run the same prompt again on the currently selected model"
                  @click="emit('regenerate', { mediaId: item.id, model: null })"
                >
                  ↻ Retry
                </button>
                <ModelPicker
                  :model-value="''"
                  :models="chatModels[item.kind] || []"
                  :kind="item.kind"
                  :label="KIND_LABEL[item.kind] || 'Video'"
                  :allow-none="false"
                  trigger-text="Try another model…"
                  @update:model-value="model => model && emit('regenerate', { mediaId: item.id, model })"
                />
              </div>
            </div>

            <!-- Which model made this — the footer only names the chat model -->
            <div v-if="item.model || item.prompt" class="media-caption">
              <span class="caption-text" :title="[item.model, ...specs(item)].join(' · ')">
                {{ KIND_ICON[item.kind] || '🎬' }} {{ shortModel(item.model)
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
                  ·
                  <span
                    class="caption-refs"
                    title=""
                    @mouseenter="showRefs($event, item.params)"
                    @mouseleave="refsPeek = null"
                    >🔗 {{ refsLabel(item.params) }}</span
                  ></template
                >
              </span>
              <button
                v-if="canRemake(item) && item.kind === 'image' && item.file"
                class="caption-btn"
                title="Edit this picture: describe the change and it is replaced here"
                @click="openPrompt(item, true)"
              >
                ✎ Edit
              </button>
              <button
                v-if="canRemake(item)"
                class="caption-btn"
                title="Make it again: tweak the prompt and it is replaced here"
                @click="openPrompt(item, false)"
              >
                ↻ Redo
              </button>
              <button
                v-if="item.prompt"
                class="caption-btn"
                :title="`Copy the prompt sent to the ${item.kind} model:\n${item.prompt}`"
                @click="copy(item.prompt, item.id)"
              >
                {{ copiedKey === item.id ? '✓ Copied' : '⧉ Prompt' }}
              </button>
              <button
                v-if="item.request"
                class="caption-btn"
                title="Show exactly what was sent to the provider"
                @click="requestItem = item"
              >
                { } Request
              </button>
            </div>
            <div v-if="promptBox?.mediaId === item.id" class="prompt-box">
              <textarea
                v-model="promptBox.text"
                v-focus-select
                rows="2"
                :placeholder="promptBox.edit ? 'Describe the change…' : 'Prompt for the new version…'"
                @keydown.enter.exact.prevent="submitPrompt(item)"
                @keydown.esc="promptBox = null"
              ></textarea>
              <div class="prompt-box-actions">
                <span class="prompt-box-hint">
                  {{ promptBox.edit ? 'Edits this picture' : 'Makes a new one from the prompt alone' }}
                </span>
                <button class="meta-btn" @click="promptBox = null">Cancel</button>
                <button class="edit-send" :disabled="!promptBox.text.trim()" @click="submitPrompt(item)">
                  {{ promptBox.edit ? 'Edit' : 'Redo' }}
                </button>
              </div>
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
            <button
              v-if="canRetry && message.media?.length"
              class="meta-btn"
              title="Write these words again, keeping the pictures this reply made"
              @click="emit('reword')"
            >
              ↻ Words
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
    <RequestDialog
      v-if="requestItem"
      :request="requestItem.request"
      :response="requestItem.response"
      :error="requestItem.status === 'error' ? requestItem.error : ''"
      @close="requestItem = null"
    />
    <Teleport to="body">
      <div v-if="refsPeek" class="refs-peek" :style="{ left: `${refsPeek.x}px`, top: `${refsPeek.y}px` }">
        <div class="refs-peek-title">{{ refsTitle(refsPeek.params) }}</div>
        <div class="refs-peek-grid">
          <img
            v-for="(r, i) in refsPeek.params.refs"
            :key="r"
            :src="refUrl(r)"
            :alt="r"
            :class="{ unused: refsPeek.params.refs_used != null && i >= refsPeek.params.refs_used }"
          />
        </div>
      </div>
    </Teleport>
  </div>
</template>

<style scoped src="./ChatMessage.css"></style>

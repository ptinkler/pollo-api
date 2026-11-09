<!-- Studio compose bar: attachments + mode pills + prompt box + send.
     Presentational — attachment list/upload state come from props.
     The prompt is a contenteditable so reference mentions ([@name]) show as
     inline pills; the [@name] text remains the source of truth. -->
<script setup>
import { ref, computed, watch, nextTick, onMounted, onBeforeUnmount } from 'vue'
import { fmtCost, creditsToUsd } from '../../utils/format'

const props = defineProps({
  modes: { type: Array, default: () => [] },
  mode: { type: String, default: 'auto' },
  draft: { type: String, default: '' },
  sending: { type: Boolean, default: false },
  canSend: { type: Boolean, default: false },
  attachments: { type: Array, default: () => [] },
  uploading: { type: Boolean, default: false },
  enhancing: { type: Boolean, default: false },
  // Pollo's price for the current setup: { credits, full_credits } or null
  estimate: { type: Object, default: null },
  // Keys of attachments the selected model can't use (dimmed, not sent)
  unused: { type: Object, default: () => new Set() },
  // The selected video model takes a source video (Recast / motion models)
  videoInput: { type: Boolean, default: false },
  // The selected video model takes an audio track (lip-sync models)
  audioInput: { type: Boolean, default: false },
  // The selected video model's reference-to-video config (image/video/audio
  // refs the prompt mentions as [@name]): { types, max, limits } or null.
  refMode: { type: Object, default: null },
})
const emit = defineEmits(['update:draft', 'update:mode', 'send', 'files', 'remove', 'clear', 'library', 'enhance'])

const drag = ref(false)
const ed = ref(null) // the contenteditable prompt
const aud = ref(null) // hidden audio-clip file input (audio mode)
const atMenu = ref(false) // the @-mention picker
const onEsc = e => e.key === 'Escape' && (atMenu.value = false)
onMounted(() => document.addEventListener('keydown', onEsc))
onBeforeUnmount(() => document.removeEventListener('keydown', onEsc))
// Audio mode with a voice-clone model: the only attachment is the reference clip
const audioClip = computed(() => props.mode === 'audio' && props.audioInput)
const mediaMode = computed(() => props.mode === 'image' || props.mode === 'video')
const refsActive = computed(() => !!props.refMode && props.mode === 'video')
const placeholder = computed(() =>
  refsActive.value
    ? 'Add instructions, e.g. replace the person in [@video1] with [@image1]'
    : 'Message, or describe an image / video…',
)
function removeUnused() {
  props.attachments.filter(a => props.unused.has(a.key)).forEach(a => emit('remove', a))
}
const cap = s => s.charAt(0).toUpperCase() + s.slice(1)
const attType = a => (a.audio ? 'audio' : a.video ? 'video' : 'image')

// Reference-to-video: each allowed attachment becomes a mentionable ref named
// by type + order (image1, video1, audio1…) — the handle the prompt uses as
// [@name]. Caps come from the model's ref_mode; ordering matches the backend
// (web/chat/turn.py _ref_items) so a pill always resolves to the same
// attachment.
const refItems = computed(() => {
  if (!refsActive.value) return []
  const types = new Set(props.refMode.types || ['image', 'video', 'audio'])
  const limits = props.refMode.limits || {}
  const counts = {}
  const out = []
  for (const a of props.attachments) {
    const type = attType(a)
    const n = (counts[type] || 0) + 1
    if (a.uploading || !types.has(type) || (limits[type] && n > limits[type])) continue
    counts[type] = n
    out.push({ key: a.key, name: `${type}${n}`, label: `${cap(type)} ${n}`, type, preview: a.preview })
    if (props.refMode.max && out.length >= props.refMode.max) break
  }
  return out
})
// Click-to-insert: map each attachment to its ref so clicking its thumbnail
// drops the [@name] pill into the prompt.
const refByKey = computed(() => Object.fromEntries(refItems.value.map(r => [r.key, r])))
const canInsert = a => !a.uploading && !!refByKey.value[a.key]
function insertAtt(a) {
  const r = refByKey.value[a.key]
  if (r) insertMention(r)
}

// ― contenteditable plumbing: [@name] text is the source of truth; a pill is
// just how a known mention is shown. We edit the DOM imperatively (re-rendering
// on every keystroke would fight the caret) and serialize back to [@name]. ―
const MENTION = /\[@([a-zA-Z0-9_]+)\]/g

// Pills are built imperatively, so Vue's scoped CSS can't reach them — style
// them inline (CSS vars resolve against the app root).
const PILL_CSS =
  'display:inline-flex;align-items:center;gap:6px;vertical-align:middle;margin:0 2px;' +
  'padding:1px 8px 1px 3px;border:1px solid var(--sborder);border-radius:8px;' +
  'background:var(--saccent-soft);color:var(--saccent);font-size:0.85em;line-height:1.5;' +
  'user-select:none;white-space:nowrap'
function makePill(refItem) {
  const span = document.createElement('span')
  span.className = 'pill'
  span.contentEditable = 'false'
  span.dataset.name = refItem.name
  span.style.cssText = PILL_CSS
  if (refItem.type === 'image' && refItem.preview) {
    const im = document.createElement('img')
    im.src = refItem.preview
    im.style.cssText = 'width:18px;height:18px;border-radius:4px;object-fit:cover;flex:none'
    span.appendChild(im)
  } else {
    const ic = document.createElement('span')
    ic.textContent = refItem.type === 'audio' ? '🔊' : '🎞'
    ic.style.fontSize = '13px'
    span.appendChild(ic)
  }
  span.appendChild(document.createTextNode(refItem.label))
  return span
}

// Text → nodes: [@name] becomes a pill when that reference is attached, else stays text
function draftNodes(text) {
  const nodes = []
  let last = 0
  let m
  MENTION.lastIndex = 0
  while ((m = MENTION.exec(text))) {
    if (m.index > last) nodes.push(document.createTextNode(text.slice(last, m.index)))
    const refItem = refItems.value.find(r => r.name === m[1])
    nodes.push(refItem ? makePill(refItem) : document.createTextNode(m[0]))
    last = MENTION.lastIndex
  }
  if (last < text.length) nodes.push(document.createTextNode(text.slice(last)))
  return nodes
}
function renderDraft(text) {
  const el = ed.value
  if (!el) return
  el.textContent = ''
  for (const node of draftNodes(text)) el.appendChild(node)
}

function nodeText(node) {
  if (node.nodeType === Node.TEXT_NODE) return node.textContent
  if (node.nodeName === 'BR') return '\n'
  if (node.classList?.contains('pill')) return `[@${node.dataset.name}]`
  let t = ''
  for (const c of node.childNodes) t += nodeText(c)
  return t
}
function serialize() {
  let out = ''
  for (const node of ed.value?.childNodes || []) out += nodeText(node)
  return out
}
function syncDraft() {
  emit('update:draft', serialize())
}

function placeCaretEnd() {
  const el = ed.value
  if (!el) return
  const range = document.createRange()
  range.selectNodeContents(el)
  range.collapse(false)
  const sel = window.getSelection()
  sel.removeAllRanges()
  sel.addRange(range)
}

function insertNode(node, trailingSpace = false) {
  const el = ed.value
  el.focus()
  const sel = window.getSelection()
  let range
  if (sel.rangeCount && el.contains(sel.anchorNode)) {
    range = sel.getRangeAt(0)
  } else {
    range = document.createRange()
    range.selectNodeContents(el)
    range.collapse(false)
  }
  range.deleteContents()
  range.insertNode(node)
  let after = node
  if (trailingSpace) {
    const space = document.createTextNode(' ')
    node.after(space)
    after = space
  }
  range.setStartAfter(after)
  range.collapse(true)
  sel.removeAllRanges()
  sel.addRange(range)
  syncDraft()
}

function insertMention(refItem) {
  atMenu.value = false
  insertNode(makePill(refItem), true)
}

// Re-render only on external draft changes (enhance, clear, resend) — not our
// own edits — so the caret isn't disturbed mid-type.
watch(
  () => props.draft,
  v => {
    if (ed.value && v !== serialize()) {
      renderDraft(v)
      nextTick(placeCaretEnd)
    }
  },
)
// Attachments changed: stale pills may need to re-pill or drop back to text.
watch(
  () => refItems.value.map(r => `${r.name}:${r.key}`).join(','),
  () => {
    if (ed.value) {
      renderDraft(serialize())
      syncDraft()
    }
  },
)
onMounted(() => renderDraft(props.draft))

function onVideo(e) {
  emit('files', e.target.files)
  e.target.value = ''
}

function onKey(e) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    emit('send')
  } else if (e.key === 'Enter' && e.shiftKey) {
    e.preventDefault()
    insertNode(document.createTextNode('\n'))
  }
}
// Copy / cut: put the selection on the clipboard as plain text with each pill
// written as its [@name] — the browser's own copy drops the pills (they're
// non-editable elements with no text of their own), leaving blanks.
function selectionText() {
  const sel = window.getSelection()
  if (!sel?.rangeCount || sel.isCollapsed || !ed.value?.contains(sel.anchorNode)) return null
  const holder = document.createElement('div')
  holder.appendChild(sel.getRangeAt(0).cloneContents())
  return nodeText(holder)
}
function onCopy(e) {
  const text = selectionText()
  if (text == null) return
  e.clipboardData.setData('text/plain', text)
  e.preventDefault()
}
function onCut(e) {
  const text = selectionText()
  if (text == null) return
  e.clipboardData.setData('text/plain', text)
  e.preventDefault()
  window.getSelection().getRangeAt(0).deleteContents()
  syncDraft()
}
// Pasted screenshots become attachments; everything else pastes as plain text
// (so copied rich markup can't get into the contenteditable).
function onPaste(e) {
  const imgs = [...(e.clipboardData?.files || [])].filter(f => f.type.startsWith('image/'))
  if (imgs.length) {
    e.preventDefault()
    return emit('files', imgs)
  }
  const text = e.clipboardData?.getData('text/plain')
  if (text != null) {
    e.preventDefault()
    // [@name] in pasted text turns into pills for the references that are attached
    for (const node of draftNodes(text)) insertNode(node)
  }
}
function onDrop(e) {
  drag.value = false
  emit('files', e.dataTransfer?.files)
}
</script>

<template>
  <div class="compose" @dragover.prevent="drag = true" @dragleave.prevent="drag = false" @drop.prevent="onDrop">
    <div class="cbox" :class="{ drag }">
      <div v-if="attachments.length || mediaMode || audioClip" class="atts">
        <div v-if="mediaMode || audioClip" class="plus">
          <button
            class="addtile"
            :title="audioClip ? 'Upload an audio clip' : 'Add references — pick from your media or upload'"
            @click="audioClip ? aud?.click() : emit('library')"
          >
            +
          </button>
        </div>
        <div
          v-for="a in attachments"
          :key="a.key"
          class="att"
          :class="{ uploading: a.uploading, ins: canInsert(a), unused: unused.has(a.key) }"
          :title="
            unused.has(a.key)
              ? 'This model can\'t use this — it won\'t be sent'
              : canInsert(a)
                ? 'Click to add this reference to the prompt'
                : ''
          "
          @click="insertAtt(a)"
        >
          <div class="att-media">
            <div v-if="a.audio" class="att-audio" title="Audio reference">🔊</div>
            <video
              v-else-if="a.video"
              :src="a.preview"
              muted
              playsinline
              disablepictureinpicture
              preload="metadata"
            ></video>
            <img v-else :src="a.preview" alt="attachment" />
          </div>
          <button class="attx" title="Remove" @click.stop="emit('remove', a)">×</button>
          <!-- Hover: a slightly larger still preview (no playback / PiP) -->
          <div class="att-zoom">
            <video v-if="a.video" :src="a.preview" muted playsinline disablepictureinpicture preload="metadata"></video>
            <span v-else-if="a.audio" class="zoom-audio">🔊</span>
            <img v-else :src="a.preview" alt="" />
          </div>
        </div>
      </div>
      <div v-if="unused.size" class="unused-note">
        {{ unused.size }} attachment{{ unused.size === 1 ? '' : 's' }} won't be sent — this model can't use
        {{ unused.size === 1 ? 'it' : 'them' }}.
        <button class="clearall" @click="removeUnused">Remove</button>
      </div>
      <div v-if="attachments.length" class="clearrow">
        <button class="clearall" title="Remove every attached image and video" @click="emit('clear')">Clear all</button>
      </div>

      <div class="modes">
        <button
          v-for="md in modes"
          :key="md.id"
          class="pillbtn"
          :class="{ on: mode === md.id }"
          @click="emit('update:mode', md.id)"
        >
          {{ md.label }}
        </button>
      </div>

      <div
        ref="ed"
        class="ed"
        contenteditable="true"
        role="textbox"
        :data-placeholder="placeholder"
        @input="syncDraft"
        @keydown="onKey"
        @paste="onPaste"
        @copy="onCopy"
        @cut="onCut"
      ></div>

      <div class="cbar">
        <div v-if="refsActive && refItems.length" class="atwrap">
          <button class="clip at" title="Mention a reference image or video" @click="atMenu = !atMenu">@</button>
          <div v-if="atMenu" class="atmenu" @mouseleave="atMenu = false">
            <button v-for="r in refItems" :key="r.key" @click="insertMention(r)">
              <img v-if="r.type === 'image'" :src="r.preview" alt="" />
              <span v-else class="pill-ic">{{ r.type === 'audio' ? '🔊' : '🎞' }}</span
              >{{ r.label }}
            </button>
          </div>
        </div>
        <button
          v-if="!mediaMode && mode !== 'audio'"
          class="clip"
          title="Attach images — pick from Media or upload"
          @click="emit('library')"
        >
          <svg class="ic"><use href="#s-clip" /></svg>
        </button>
        <input ref="aud" type="file" accept="audio/*" hidden @change="onVideo" />
        <button
          v-if="mode === 'image' || mode === 'video'"
          class="clip enh"
          :disabled="!draft.trim() || enhancing"
          title="Enhance the prompt with the text model (optional — sending uses the prompt exactly as written)"
          @click="emit('enhance')"
        >
          {{ enhancing ? '…' : '✨' }}
        </button>
        <span class="note">{{ uploading ? 'Uploading…' : '' }}</span>
        <span
          v-if="estimate && (mediaMode || mode === 'audio')"
          class="est"
          :title="
            estimate.full_credits > estimate.credits
              ? `Pollo's estimate: ${estimate.credits} credits (${estimate.full_credits} before discount)`
              : `Pollo's estimate: ${estimate.credits} credits`
          "
          >≈ {{ fmtCost(creditsToUsd(estimate.credits)) }}</span
        >
        <button class="sendbtn" :disabled="!canSend" @click="emit('send')">{{ sending ? 'Sending…' : 'Send' }}</button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.clearrow {
  position: absolute;
  top: 10px;
  right: 12px;
  z-index: 2;
}
.clearall {
  border: 1px solid var(--sborder);
  border-radius: 999px;
  background: var(--sbg);
  color: var(--smuted);
  font: inherit;
  font-size: 11px;
  padding: 2px 9px;
  cursor: pointer;
}
.clearall:hover {
  color: var(--sdanger);
  border-color: var(--sdanger);
}
.est {
  font-size: 12.5px;
  color: var(--saccent);
  white-space: nowrap;
}
.est.warn {
  color: var(--swarn);
  cursor: help;
}
.compose {
  padding: 8px 22px 20px;
}
.cbox {
  position: relative;
  max-width: 820px;
  margin: 0 auto;
  border: 1px solid var(--sborder);
  background: var(--sbg);
  border-radius: var(--r-lg);
  padding: 10px 12px 8px;
}
.cbox:focus-within {
  border-color: var(--sfaint);
}
.cbox.drag {
  border-color: var(--saccent);
  background: var(--saccent-soft);
}
.atts {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  padding-bottom: 8px;
}
.att {
  position: relative;
  width: 52px;
  height: 52px;
}
.att.unused {
  opacity: 0.4;
  filter: grayscale(1);
}
.unused-note {
  padding: 2px 12px 6px;
  font-size: 12px;
  color: var(--swarn);
}
.att.ins {
  cursor: pointer;
}
.att-media {
  width: 100%;
  height: 100%;
  border-radius: 9px;
  overflow: hidden;
  border: 1px solid var(--sborder);
}
.att.ins:hover .att-media {
  border-color: var(--saccent);
}
.att-media video,
.att-media img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}
.att-audio {
  width: 100%;
  height: 100%;
  display: grid;
  place-items: center;
  font-size: 22px;
  background: var(--saccent-soft);
}
/* Hover: a larger still preview floating above the thumbnail */
.att-zoom {
  position: absolute;
  bottom: calc(100% + 6px);
  left: 50%;
  transform: translateX(-50%);
  display: none;
  z-index: 30;
  padding: 3px;
  background: var(--spanel2);
  border: 1px solid var(--sborder);
  border-radius: var(--r);
  box-shadow: var(--shadow-pop);
}
.att:hover .att-zoom {
  display: block;
}
.att-zoom img,
.att-zoom video {
  display: block;
  max-width: 200px;
  max-height: 200px;
  border-radius: 5px;
}
.zoom-audio {
  display: grid;
  place-items: center;
  width: 120px;
  height: 64px;
  font-size: 30px;
}
.plus {
  position: relative;
}
.addtile {
  width: 52px;
  height: 52px;
  border-radius: 9px;
  border: 1px dashed var(--sborder);
  background: var(--sbg2);
  color: var(--smuted);
  font-size: 22px;
  cursor: pointer;
}
.addtile:hover {
  border-color: var(--saccent);
  color: var(--sfg);
}
.att.uploading {
  opacity: 0.5;
}
.attx {
  position: absolute;
  top: 2px;
  right: 2px;
  width: 17px;
  height: 17px;
  display: grid;
  place-items: center;
  border: none;
  border-radius: 5px;
  background: rgba(0, 0, 0, 0.6);
  color: #fff;
  cursor: pointer;
  font-size: 13px;
  line-height: 1;
}
.modes {
  display: flex;
  gap: 6px;
  padding-bottom: 8px;
}
.ed {
  width: 100%;
  color: var(--sfg);
  outline: none;
  min-height: 22px;
  max-height: 45vh;
  overflow-y: auto;
  font: inherit;
  line-height: 1.5;
  white-space: pre-wrap;
  word-break: break-word;
}
.ed:empty::before {
  content: attr(data-placeholder);
  color: var(--sfaint);
  pointer-events: none;
}
/* Inline reference mention, e.g. [@video1] — styled like the old chip */
.pill {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  vertical-align: middle;
  margin: 0 2px;
  padding: 2px 10px 2px 3px;
  border: 1px solid var(--sborder);
  border-radius: 8px;
  background: var(--saccent-soft);
  color: var(--saccent);
  font-size: 0.86em;
  user-select: none;
  white-space: nowrap;
}
.pill img {
  width: 20px;
  height: 20px;
  border-radius: 5px;
  object-fit: cover;
}
.pill-ic {
  font-size: 14px;
}
.cbar {
  display: flex;
  align-items: center;
  gap: 10px;
  padding-top: 6px;
}
.atwrap {
  position: relative;
}
.clip.at {
  font-size: 18px;
  font-weight: 700;
}
.atmenu {
  position: absolute;
  bottom: 40px;
  left: 0;
  z-index: 20;
  min-width: 150px;
  max-height: 240px;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  background: var(--spanel2);
  border: 1px solid var(--sborder);
  border-radius: var(--r-lg);
  padding: 4px;
  box-shadow: var(--shadow-pop);
}
.atmenu button {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  text-align: left;
  border: none;
  background: none;
  color: var(--sfg);
  font: inherit;
  font-size: 13px;
  padding: 6px 9px;
  border-radius: 7px;
  cursor: pointer;
}
.atmenu button:hover {
  background: var(--shover);
}
.atmenu img {
  width: 22px;
  height: 22px;
  border-radius: 5px;
  object-fit: cover;
}
.clip {
  width: 30px;
  height: 30px;
  display: grid;
  place-items: center;
  border-radius: 8px;
  color: var(--smuted);
  background: none;
  border: none;
  cursor: pointer;
}
.clip:hover {
  background: var(--shover);
  color: var(--sfg);
}
.note {
  flex: 1;
  font-size: 12px;
  color: var(--sfaint);
}
.sendbtn {
  min-height: 30px;
  padding: 5px 14px;
  border: none;
  border-radius: var(--r);
  background: var(--saccent);
  color: #fff;
  cursor: pointer;
  font-weight: 600;
}
.sendbtn:hover:not(:disabled) {
  filter: brightness(1.08);
}
.sendbtn:disabled {
  opacity: 0.4;
  cursor: default;
}
</style>

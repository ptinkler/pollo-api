<!-- Studio compose bar: attachments + mode pills + prompt box + send.
     Presentational — attachment list/upload state come from props. -->
<script setup>
import { ref, computed, watch, nextTick, onMounted, onBeforeUnmount } from 'vue'

const props = defineProps({
  modes: { type: Array, default: () => [] },
  mode: { type: String, default: 'auto' },
  draft: { type: String, default: '' },
  hint: { type: String, default: '' },
  sending: { type: Boolean, default: false },
  canSend: { type: Boolean, default: false },
  attachments: { type: Array, default: () => [] },
  uploading: { type: Boolean, default: false },
  enhancing: { type: Boolean, default: false },
  // Pollo's price for the current setup: { credits, full_credits } or null
  estimate: { type: Object, default: null },
  // The selected video model takes a source video (Recast / motion models)
  videoInput: { type: Boolean, default: false },
})
const emit = defineEmits(['update:draft', 'update:mode', 'send', 'files', 'remove', 'clear', 'library', 'enhance'])

const drag = ref(false)
const ta = ref(null)
const vid = ref(null)
const img = ref(null)
const menu = ref(false)
const peek = ref(null)
const onEsc = e => e.key === 'Escape' && (peek.value = null)
onMounted(() => document.addEventListener('keydown', onEsc))
onBeforeUnmount(() => document.removeEventListener('keydown', onEsc))
const mediaMode = computed(() => props.mode === 'image' || props.mode === 'video')
const pick = fn => {
  menu.value = false
  fn()
}
// "Image 1", "Image 2"… — the names a prompt can use to point at each reference
const tags = computed(() => {
  let n = 0
  return props.attachments
    .filter(a => !a.video)
    .map(a => ({ key: a.key, preview: a.preview, label: `Image ${++n}`, video: a.video }))
})
function mention(label) {
  const d = props.draft
  emit('update:draft', `${d}${d && !d.endsWith(' ') ? ' ' : ''}${label} `)
  ta.value?.focus()
}
function onVideo(e) {
  emit('files', e.target.files)
  e.target.value = ''
}

// Grow the prompt box with its content up to the CSS max-height, then scroll.
function autogrow() {
  const el = ta.value
  if (!el) return
  el.style.height = 'auto'
  el.style.height = `${el.scrollHeight}px`
}
watch(
  () => props.draft,
  () => nextTick(autogrow),
)
onMounted(autogrow)

// A method (not two inline statements) so a prettier reformat can't break the
// template handler by splitting it across lines without a separator.
function onInput(e) {
  emit('update:draft', e.target.value)
  autogrow()
}

function onKey(e) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    emit('send')
  }
}
// Pasted screenshots / copied images become attachments (text pastes pass through)
function onPaste(e) {
  const imgs = [...(e.clipboardData?.files || [])].filter(f => f.type.startsWith('image/'))
  if (!imgs.length) return
  e.preventDefault()
  emit('files', imgs)
}
function onDrop(e) {
  drag.value = false
  emit('files', e.dataTransfer?.files)
}
</script>

<template>
  <div class="compose" @dragover.prevent="drag = true" @dragleave.prevent="drag = false" @drop.prevent="onDrop">
    <div class="cbox" :class="{ drag }">
      <div v-if="attachments.length || mediaMode" class="atts">
        <div v-if="mediaMode" class="plus">
          <button class="addtile" title="Add reference images" @click="menu = !menu">+</button>
          <div v-if="menu" class="addmenu" @mouseleave="menu = false">
            <button @click="pick(() => emit('library'))">🖼 From Media…</button>
            <button @click="pick(() => img?.click())">⬆ Upload image</button>
            <button v-if="mode === 'video' && videoInput" @click="pick(() => vid?.click())">🎞 Upload video</button>
          </div>
        </div>
        <div v-for="a in attachments" :key="a.key" class="att" :class="{ uploading: a.uploading }">
          <video v-if="a.video" :src="a.preview" muted playsinline @click="peek = a"></video>
          <img v-else :src="a.preview" alt="attachment" title="Click to enlarge" @click="peek = a" />
          <button class="attx" title="Remove" @click="emit('remove', a)">×</button>
        </div>
      </div>
      <div v-if="attachments.length" class="clearrow">
        <button class="clearall" title="Remove every attached image and video" @click="emit('clear')">Clear all</button>
      </div>
      <div v-if="tags.length" class="tags">
        <button v-for="t in tags" :key="t.key" class="tag" title="Insert into the prompt" @click="mention(t.label)">
          <img v-if="!t.video" :src="t.preview" alt="" />{{ t.label }}
        </button>
      </div>

      <div class="modes">
        <button
          v-for="md in modes"
          :key="md.id"
          class="modepill"
          :class="{ on: mode === md.id }"
          @click="emit('update:mode', md.id)"
        >
          {{ md.label }}
        </button>
      </div>

      <textarea
        ref="ta"
        :value="draft"
        rows="1"
        placeholder="Message, or describe an image / video…"
        @input="onInput"
        @keydown="onKey"
        @paste="onPaste"
      ></textarea>

      <div class="cbar">
        <button
          v-if="!mediaMode"
          class="clip"
          title="Attach images — pick from Media or upload"
          @click="emit('library')"
        >
          <svg class="ic"><use href="#s-clip" /></svg>
        </button>
        <input ref="vid" type="file" accept="video/mp4" hidden @change="onVideo" />
        <input ref="img" type="file" accept="image/*" multiple hidden @change="onVideo" />
        <button
          v-if="mode === 'image' || mode === 'video'"
          class="clip enh"
          :disabled="!draft.trim() || enhancing"
          title="Enhance the prompt with the text model (optional — sending uses the prompt exactly as written)"
          @click="emit('enhance')"
        >
          {{ enhancing ? '…' : '✨' }}
        </button>
        <span class="note">{{ uploading ? 'Uploading…' : hint }}</span>
        <span
          v-if="estimate && mediaMode"
          class="est"
          :title="
            estimate.full_credits > estimate.credits
              ? `Pollo's estimate (${estimate.full_credits} before discount)`
              : 'Pollo\'s estimate for these settings'
          "
          >≈ {{ estimate.credits }} cr</span
        >
        <button class="sendbtn" :disabled="!canSend" @click="emit('send')">{{ sending ? 'Sending…' : 'Send' }}</button>
      </div>
    </div>
    <div v-if="peek" class="peek" @click="peek = null" @keydown.esc="peek = null">
      <video v-if="peek.video" :src="peek.preview" controls autoplay loop @click.stop></video>
      <img v-else :src="peek.preview" alt="attachment preview" @click.stop />
    </div>
  </div>
</template>

<style scoped>
.clearrow {
  display: flex;
  justify-content: flex-end;
  padding-bottom: 6px;
}
.clearall {
  border: 1px solid var(--sborder);
  border-radius: 999px;
  background: none;
  color: var(--smuted);
  font: inherit;
  font-size: 12px;
  padding: 3px 10px;
  cursor: pointer;
}
.clearall:hover {
  color: var(--sdanger, #e5484d);
  border-color: var(--sdanger, #e5484d);
}
.est {
  font-size: 12.5px;
  color: var(--saccent);
  white-space: nowrap;
}
.peek {
  position: fixed;
  inset: 0;
  z-index: 1000;
  display: grid;
  place-items: center;
  background: rgba(0, 0, 0, 0.7);
  cursor: zoom-out;
}
.peek img,
.peek video {
  max-width: min(90vw, 900px);
  max-height: 85vh;
  object-fit: contain;
  border-radius: 10px;
  cursor: default;
}
.att img,
.att video {
  cursor: zoom-in;
}
.compose {
  padding: 8px 22px 20px;
}
.cbox {
  max-width: 820px;
  margin: 0 auto;
  border: 1px solid var(--sborder);
  background: var(--sbg);
  border-radius: 14px;
  padding: 10px 12px;
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
  border-radius: 9px;
  overflow: hidden;
  border: 1px solid var(--sborder);
}
.att video,
.att img {
  width: 100%;
  height: 100%;
  object-fit: cover;
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
.addmenu {
  position: absolute;
  bottom: 58px;
  left: 0;
  z-index: 20;
  min-width: 160px;
  display: flex;
  flex-direction: column;
  background: var(--spanel2, var(--sbg2));
  border: 1px solid var(--sborder);
  border-radius: 10px;
  padding: 4px;
  box-shadow: 0 10px 28px rgba(0, 0, 0, 0.4);
}
.addmenu button {
  text-align: left;
  border: none;
  background: none;
  color: var(--sfg);
  font: inherit;
  font-size: 13px;
  padding: 7px 10px;
  border-radius: 7px;
  cursor: pointer;
}
.addmenu button:hover {
  background: var(--shover);
}
.tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  padding-bottom: 8px;
}
.tag {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 2px 10px 2px 3px;
  border: 1px solid var(--sborder);
  border-radius: 8px;
  background: var(--saccent-soft);
  color: var(--saccent);
  font: inherit;
  font-size: 12.5px;
  cursor: pointer;
}
.tag img {
  width: 20px;
  height: 20px;
  border-radius: 5px;
  object-fit: cover;
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
.modepill {
  padding: 4px 11px;
  border: 1px solid var(--sborder);
  border-radius: 8px;
  color: var(--smuted);
  background: none;
  cursor: pointer;
  font-size: 12px;
}
.modepill.on {
  background: var(--saccent-soft);
  color: var(--saccent);
  border-color: transparent;
}
textarea {
  width: 100%;
  border: none;
  background: none;
  color: var(--sfg);
  resize: none;
  outline: none;
  min-height: 24px;
  max-height: 45vh;
  overflow-y: auto;
  font: inherit;
}
.cbar {
  display: flex;
  align-items: center;
  gap: 10px;
  padding-top: 8px;
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
  padding: 7px 16px;
  border: none;
  border-radius: 9px;
  background: var(--saccent);
  color: #fff;
  cursor: pointer;
  font-weight: 600;
}
.sendbtn:disabled {
  opacity: 0.4;
  cursor: default;
}
</style>

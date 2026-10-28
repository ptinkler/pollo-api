<!-- Studio compose bar: attachments + mode pills + prompt box + send.
     Presentational — attachment list/upload state come from props. -->
<script setup>
import { ref } from 'vue'

defineProps({
  modes: { type: Array, default: () => [] },
  mode: { type: String, default: 'auto' },
  draft: { type: String, default: '' },
  hint: { type: String, default: '' },
  sending: { type: Boolean, default: false },
  canSend: { type: Boolean, default: false },
  attachments: { type: Array, default: () => [] },
  uploading: { type: Boolean, default: false },
})
const emit = defineEmits(['update:draft', 'update:mode', 'send', 'files', 'remove'])

const fileInput = ref(null)
const drag = ref(false)

function onKey(e) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    emit('send')
  }
}
function pick() {
  fileInput.value?.click()
}
function onPick(e) {
  emit('files', e.target.files)
  e.target.value = ''
}
function onDrop(e) {
  drag.value = false
  emit('files', e.dataTransfer?.files)
}
</script>

<template>
  <div class="compose" @dragover.prevent="drag = true" @dragleave.prevent="drag = false" @drop.prevent="onDrop">
    <div class="cbox" :class="{ drag }">
      <div v-if="attachments.length" class="atts">
        <div v-for="a in attachments" :key="a.key" class="att" :class="{ uploading: a.uploading }">
          <img :src="a.preview" alt="attachment" />
          <button class="attx" title="Remove" @click="emit('remove', a)">×</button>
        </div>
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
        :value="draft"
        rows="1"
        placeholder="Message, or describe an image / video…"
        :disabled="sending"
        @input="emit('update:draft', $event.target.value)"
        @keydown="onKey"
      ></textarea>

      <div class="cbar">
        <button class="clip" title="Attach image" @click="pick">
          <svg class="ic"><use href="#s-clip" /></svg>
        </button>
        <span class="note">{{ uploading ? 'Uploading…' : hint }}</span>
        <button class="sendbtn" :disabled="!canSend" @click="emit('send')">{{ sending ? 'Sending…' : 'Send' }}</button>
      </div>

      <input ref="fileInput" type="file" accept="image/*" multiple hidden @change="onPick" />
    </div>
  </div>
</template>

<style scoped>
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
.att img {
  width: 100%;
  height: 100%;
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
  max-height: 180px;
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

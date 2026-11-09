<!-- Create / edit a preset (same modal pattern as characters): a name plus the
     mode, models and media options it holds — all editable. A new one starts
     from the current setup. -->
<script setup>
import { computed, inject, nextTick, reactive, ref, watch } from 'vue'
import BaseDialog from '../BaseDialog.vue'
import ModelPicker from '../chat/ModelPicker.vue'
import { confirmDialog } from '../../composables/useDialog'
import { MODES } from '../../composables/useComposerSettings'

const props = defineProps({
  open: { type: Boolean, default: false },
  preset: { type: Object, default: null }, // null = a new one
})
const emit = defineEmits(['close'])
const { snapshot, savePreset, updatePreset, deletePreset, loadPreset } = inject('composerSettings')
const models = inject('chatModels')

const clone = o => JSON.parse(JSON.stringify(o))
const name = ref('')
const d = reactive(clone(snapshot()))
const nameInput = ref(null)
const isNew = computed(() => !props.preset)

function fill(src) {
  Object.assign(
    d,
    clone({
      mode: src.mode,
      models: src.models,
      imageOpts: src.imageOpts,
      videoOpts: src.videoOpts,
      audioOpts: src.audioOpts,
    }),
  )
}
watch(
  () => props.open,
  async open => {
    if (!open) return
    name.value = props.preset?.name || ''
    fill(props.preset || snapshot())
    await nextTick()
    nameInput.value?.focus()
  },
)

// What the picked image / video model offers
const info = kind => models[kind]?.find(m => m.id === d.models[kind]) || null
const imageInfo = computed(() => info('image'))
const videoInfo = computed(() => info('video'))
const imageRatios = computed(() => imageInfo.value?.aspect_ratios || [])
const imageResolutions = computed(() => imageInfo.value?.resolutions || [])
const videoRatios = computed(() => videoInfo.value?.aspect_ratios || [])
const videoResolutions = computed(() => videoInfo.value?.resolutions || [])
const videoLengths = computed(() => videoInfo.value?.durations || [])

function save() {
  const n = name.value.trim()
  if (!n) return
  const data = clone({
    mode: d.mode,
    models: d.models,
    imageOpts: d.imageOpts,
    videoOpts: d.videoOpts,
    audioOpts: d.audioOpts,
  })
  if (isNew.value) savePreset(n, data)
  else updatePreset(props.preset.id, { name: n, ...data })
  emit('close')
}
async function remove() {
  const ok = await confirmDialog({ title: `Delete “${props.preset.name}”?`, confirmLabel: 'Delete', danger: true })
  if (!ok) return
  deletePreset(props.preset.id)
  emit('close')
}
function load() {
  loadPreset(props.preset)
  emit('close')
}
</script>

<template>
  <BaseDialog
    :open="open"
    :title="isNew ? 'New preset' : preset.name"
    label="Preset"
    width="520px"
    @close="emit('close')"
  >
    <p class="sub">
      A saved set of models and media options, loaded in one click from the Presets box above the models.
      {{ isNew ? 'It starts from your current setup — change anything below.' : '' }}
    </p>

    <label for="preset-name">Name</label>
    <input
      id="preset-name"
      ref="nameInput"
      v-model="name"
      maxlength="60"
      placeholder="e.g. Recast – Seedance 2.5"
      @keydown.enter="save"
    />

    <label for="preset-mode">Mode</label>
    <select id="preset-mode" v-model="d.mode">
      <option v-for="m in MODES" :key="m.id" :value="m.id">{{ m.label }}</option>
    </select>

    <label>Models</label>
    <div class="pickers">
      <ModelPicker v-model="d.models.text" :models="models.text" label="Chat" kind="text" :allow-none="false" />
      <ModelPicker v-model="d.models.image" :models="models.image" label="Image" kind="image" />
      <ModelPicker v-model="d.models.video" :models="models.video" label="Video" kind="video" />
      <ModelPicker v-model="d.models.audio" :models="models.audio" label="Audio" kind="audio" />
    </div>

    <label>Image options</label>
    <div class="row">
      <select v-model="d.imageOpts.aspect_ratio" :disabled="!imageRatios.length">
        <option value="">Ratio: auto</option>
        <option v-for="r in imageRatios" :key="r" :value="r">{{ r }}</option>
      </select>
      <select v-model="d.imageOpts.resolution" :disabled="!imageResolutions.length">
        <option value="">Res: default</option>
        <option v-for="r in imageResolutions" :key="r" :value="r">{{ r }}</option>
      </select>
    </div>

    <label>Video options</label>
    <div class="row">
      <select v-model="d.videoOpts.aspect_ratio" :disabled="!videoRatios.length">
        <option value="">Ratio: auto</option>
        <option v-for="r in videoRatios" :key="r" :value="r">{{ r }}</option>
      </select>
      <select v-model="d.videoOpts.resolution" :disabled="!videoResolutions.length">
        <option value="">Res: default</option>
        <option v-for="r in videoResolutions" :key="r" :value="r">{{ r }}</option>
      </select>
    </div>
    <div class="row">
      <select v-model="d.videoOpts.duration" :disabled="!videoLengths.length">
        <option value="">Length: auto</option>
        <option v-for="n in videoLengths" :key="n" :value="n">{{ n }}s</option>
      </select>
      <select v-model="d.videoOpts.generate_audio" :disabled="!videoInfo?.generate_audio">
        <option :value="true">Audio: on</option>
        <option :value="false">Audio: off</option>
      </select>
    </div>

    <button v-if="!isNew" type="button" class="btn btn-secondary replace" @click="fill(snapshot())">
      Replace with the current setup
    </button>

    <template #actions>
      <button v-if="!isNew" class="btn btn-danger" @click="remove">Delete</button>
      <button v-if="!isNew" class="btn btn-secondary" @click="load">Load</button>
      <span class="spacer"></span>
      <button class="btn btn-secondary" @click="emit('close')">Cancel</button>
      <button class="btn btn-primary" :disabled="!name.trim()" @click="save">{{ isNew ? 'Create' : 'Save' }}</button>
    </template>
  </BaseDialog>
</template>

<style scoped>
.sub {
  font-size: 0.8rem;
  color: var(--text2);
  margin-bottom: 8px;
  line-height: 1.45;
}
label {
  font-size: 0.75rem;
  color: var(--text2);
  text-transform: uppercase;
  letter-spacing: 0.04em;
  margin-top: 4px;
}
input,
select {
  width: 100%;
  padding: 9px 11px;
  border-radius: 8px;
  border: 1px solid var(--border);
  background: var(--surface2);
  color: var(--text);
  font: inherit;
  font-size: 0.9rem;
}
select:disabled {
  opacity: 0.5;
}
.pickers {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.row {
  display: flex;
  gap: 8px;
}
.row select {
  flex: 1;
  min-width: 0;
}
.replace {
  align-self: flex-start;
  padding: 6px 12px;
  font-size: 0.8rem;
}
</style>

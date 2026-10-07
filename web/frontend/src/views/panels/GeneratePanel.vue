<script setup>
import { ref, computed, watch, inject } from 'vue'
import { RatioPicker, LengthSlider, ToggleSwitch, SleekTextarea, SleekSelect, SleekInput } from '../../components/form'
import { generateVideo, generateImage, uploadSourceImage, deleteSourceImage, uploadRefImage, fetchCreditEstimate, localImageFilename, getLocalImagePreviewUrl } from '../../composables/useApi'
import { useProjectSettings } from '../../composables/useProjectSettings'
import { useJobsQueue } from '../../composables/useJobsQueue'
import { useShowHidden } from '../../composables/useShowHidden'

const props = defineProps({
  project: { type: String, required: true },
  projectData: { type: Object, default: null },
  models: { type: Object, default: () => ({}) },
  legacyMode: { type: Boolean, default: false },
  regenerateJob: { type: Object, default: null },
  useAsRef: { type: Object, default: null },
})

const emit = defineEmits(['regenerate-applied', 'use-as-ref-applied', 'update:legacy-mode'])

const showToast = inject('showToast')
const { addJob } = useJobsQueue()

// Form state
const projectRef = computed(() => props.project)
const { settings, save: saveSettings, applyProjectData, applyJobSettings } = useProjectSettings(projectRef)

const prompt = ref('')
const isSubmitting = ref(false)
const submitStatus = ref('')  // '', 'uploading', 'starting'
const submitButtonText = computed(() => {
  let text = '🚀 Generate'
  if (submitStatus.value === 'uploading') text = 'Uploading'
  else if (submitStatus.value === 'starting') text = 'Starting'
  if (creditEstimate.value?.credits != null) text += ` (~${creditEstimate.value.credits} credits)`
  return text
})

// Model options
const selectedModel = computed(() => props.models[settings.value.model] || {})
const modelType = computed(() => selectedModel.value.type || 'img2vid')

// Ref mode: legacy-API ref models are their own "type: ref" models, while v1
// models take refs on their regular endpoint when "Ref mode" is toggled on.
// Its limits come from the model's "ref_mode" (see MODEL_INFO in web/api.py).
const refModeInfo = computed(() => selectedModel.value.ref_mode || null)
const inV1RefMode = computed(() => !!refModeInfo.value && !!settings.value.ref_mode)
const showRefFields = computed(() => modelType.value === 'ref' || inV1RefMode.value)
const refHiddenOptions = computed(() => inV1RefMode.value ? (refModeInfo.value.hide_options || []) : [])

const modelLengths = computed(() => (inV1RefMode.value && refModeInfo.value.lengths) || selectedModel.value.lengths || [])
const modelRatios = computed(() => selectedModel.value.ratios || [])
const modelOptions = computed(() => (selectedModel.value.options || []).filter(o => !refHiddenOptions.value.includes(o)))

const showAudioOption = computed(() => modelOptions.value.includes('generate_audio'))
const showWebSearchOption = computed(() => modelOptions.value.includes('web_search') && !inV1RefMode.value)
const showImageTailOption = computed(() => modelOptions.value.includes('image_tail') && !inV1RefMode.value)
const showSeedOption = computed(() => modelOptions.value.includes('seed'))
const showMaxImagesOption = computed(() => modelOptions.value.includes('max_images'))
const modelResolutions = computed(() => (inV1RefMode.value && refModeInfo.value.resolutions) || selectedModel.value.resolutions || null)
const showResolution = computed(() => modelType.value !== 'image' || !!modelResolutions.value)
const resolutions = computed(() => modelResolutions.value || ['480p', '720p', '1080p'])
const showVideoNumOption = computed(() => modelOptions.value.includes('video_num'))
const showThinkingLevelOption = computed(() => modelOptions.value.includes('thinking_level'))
const isDeprecatedModel = computed(() => !!selectedModel.value.deprecated)

// Credit cost estimate — Pollo has no pre-flight pricing API, so this looks up
// what identical past generations actually cost and shows that on the button.
const creditEstimate = ref(null)
const estimateParams = computed(() => ({
  model: settings.value.model,
  resolution: showResolution.value ? settings.value.resolution : null,
  length: modelLengths.value.length > 0 ? settings.value.length : null,
  generate_audio: showAudioOption.value ? settings.value.generate_audio : null,
}))
let estimateDebounce = null
let estimateToken = 0
watch(estimateParams, (params) => {
  clearTimeout(estimateDebounce)
  if (!params.model) {
    creditEstimate.value = null
    return
  }
  const token = ++estimateToken
  estimateDebounce = setTimeout(async () => {
    try {
      const result = await fetchCreditEstimate(params)
      if (token === estimateToken) creditEstimate.value = result
    } catch {
      if (token === estimateToken) creditEstimate.value = null
    }
  }, 300)
}, { immediate: true, deep: true })

// Source image upload
const isUploading = ref(false)
const fileInputRef = ref(null)
// Preview of an image uploaded into the project ("local:<file>"), else null
const previewUrl = (url) => getLocalImagePreviewUrl(props.project, url)
const sourceImagePreviewUrl = computed(() => previewUrl(settings.value.image_url))

function triggerFileInput() {
  fileInputRef.value?.click()
}

async function handleFileUpload(event) {
  const file = event.target.files?.[0]
  if (!file) return
  event.target.value = ''

  isUploading.value = true
  try {
    const [result, bitmap] = await Promise.all([
      uploadSourceImage(props.project, file),
      createImageBitmap(file),
    ])
    settings.value.image_url = result.image_url  // "local:src-abc123.jpg"
    if (modelRatios.value.length) {
      const { width, height } = bitmap
      bitmap.close()
      const imageRatio = width / height
      settings.value.aspect_ratio = modelRatios.value.reduce((best, r) => {
        const [a, b] = r.split(':').map(Number)
        const [ba, bb] = best.split(':').map(Number)
        return Math.abs(a / b - imageRatio) < Math.abs(ba / bb - imageRatio) ? r : best
      })
    }
    showToast('Source image uploaded', 'success')
  } catch (err) {
    showToast('Upload failed: ' + err.message, 'error')
  } finally {
    isUploading.value = false
  }
}

async function removeSourceImage() {
  try {
    await deleteSourceImage(props.project, localImageFilename(settings.value.image_url))
    settings.value.image_url = ''
    showToast('Source image removed', 'success')
  } catch (err) {
    showToast('Failed to remove: ' + err.message, 'error')
  }
}

// Map deprecated pollo models to their seedance equivalents
const DEPRECATED_REMAP = {
  pollodance20: 'seedance20fast',
  pollodance20fast: 'seedance20fast',
  pollodanceref: 'seedanceref',
  pollodancereffast: 'seedancereffast',
}

// Two-word brand prefixes that shouldn't be split at the first space when
// deriving a dropdown group from a model's label (e.g. "Nano Banana 2").
const MULTI_WORD_BRANDS = ['Nano Banana']

function modelGroup(label) {
  const brand = MULTI_WORD_BRANDS.find((b) => label.startsWith(b))
  return brand || label.split(' ')[0]
}

// Format models for SleekSelect — hide deprecated models, and models not
// enabled for this API key (`hidden`) unless "Show hidden" is on; grouped by brand
const { showHidden } = useShowHidden()
const hiddenModelCount = computed(() => Object.values(props.models).filter(i => i.hidden && !i.deprecated).length)
const modelSelectOptions = computed(() => {
  return Object.entries(props.models)
    .filter(([key, info]) => !info.deprecated && (!info.hidden || showHidden.value || key === settings.value.model))
    .map(([key, info]) => ({
      value: key,
      label: `${info.label}${info.type === 'ref' ? ' (ref)' : ''}${info.hidden ? ' (not enabled)' : ''}`,
      group: modelGroup(info.label)
    }))
})

// Watch for project data changes
watch(() => props.projectData, (data) => {
  if (data) {
    prompt.value = data.prompt || ''
    applyProjectData(data)
  }
}, { immediate: true })

// Watch for regenerate job - apply settings from the job being regenerated
watch(() => props.regenerateJob, (job) => {
  if (job) {
    prompt.value = job.prompt || ''
    applyJobSettings(job)
    const remapped = DEPRECATED_REMAP[settings.value.model]
    if (remapped) settings.value.model = remapped
    emit('regenerate-applied')
    showToast('Settings loaded from video', 'success')
  }
}, { immediate: true })

// Watch for use-as-ref - switch to ref model and prefill refs
watch(() => props.useAsRef, (data) => {
  if (data) {
    const refs = data.refs || []
    if (props.models.seedanceref) {
      settings.value.model = 'seedanceref'
    } else {
      // v1: keep the current model if its ref mode takes these refs, else Seedance 2.0
      const types = props.models[settings.value.model]?.ref_mode?.types || []
      if (!refs.every(r => types.includes(r.type))) settings.value.model = 'seedance20v1'
      settings.value.ref_mode = true
    }
    settings.value.refs = refs
    if (data.prompt) {
      prompt.value = data.prompt
    }
    emit('use-as-ref-applied')
    showToast('Video added as reference', 'success')
  }
}, { immediate: true })

// Toggling legacy mode swaps the entire models list (legacy and v1 model
// keys are disjoint — see MODEL_INFO in web/api.py) — fall back to
// whatever model comes first in the new list if the current selection
// no longer exists in it.
watch(() => props.models, (newModels) => {
  const keys = Object.keys(newModels || {})
  if (keys.length && !newModels[settings.value.model]) {
    settings.value.model = keys[0]
  }
})

// Ensure length is valid when model changes
watch(modelLengths, (lengths) => {
  if (lengths.length && !lengths.includes(settings.value.length)) {
    settings.value.length = lengths[Math.floor(lengths.length / 2)]
  }
})

// Ensure ratio is valid when model changes
watch(modelRatios, (ratios) => {
  if (ratios.length && !ratios.includes(settings.value.aspect_ratio)) {
    settings.value.aspect_ratio = ratios[0]
  }
})

// Ensure resolution is valid when model changes, defaulting to lowest
watch(resolutions, (res) => {
  if (res.length && !res.includes(settings.value.resolution)) {
    settings.value.resolution = res[0]
  }
})

// --- Refs management for ref2video ---
const REF_TYPE_LABELS = {
  image: 'Image', subject: 'Subject', video: 'Video', audio: 'Audio', file: 'Document', link: 'Web page',
}
const REF_URL_PLACEHOLDERS = {
  file: 'https://example.com/document.pdf',
  link: 'https://example.com/page',
}
const refTypes = computed(() =>
  (inV1RefMode.value ? refModeInfo.value.types : ['image', 'subject', 'video', 'audio'])
    .map(value => ({ value, label: REF_TYPE_LABELS[value] || value }))
)
const maxRefs = computed(() => inV1RefMode.value ? refModeInfo.value.max : 13)

function newRefItem(type = 'image') {
  const order = settings.value.refs.length + 1
  if (type === 'subject') {
    return { type: 'subject', name: '', images: [{ url: '' }], subjectId: '' }
  }
  // image, video, audio all share the same shape: url + order
  return { type, name: '', url: '', order }
}

function addRef() {
  if (settings.value.refs.length >= maxRefs.value) return
  settings.value.refs.push(newRefItem('image'))
}

function removeRef(index) {
  settings.value.refs.splice(index, 1)
  // Reorder non-subject refs
  let order = 1
  settings.value.refs.forEach(r => {
    if (r.type !== 'subject') { r.order = order++ }
  })
}

function onRefTypeChange(index) {
  const old = settings.value.refs[index]
  const fresh = newRefItem(old.type)
  fresh.name = old.name // preserve name
  settings.value.refs.splice(index, 1, fresh)
}

function addSubjectImage(refItem) {
  if (refItem.images.length < 3) {
    refItem.images.push({ url: '' })
  }
}

function removeSubjectImage(refItem, imgIndex) {
  if (refItem.images.length > 1) {
    refItem.images.splice(imgIndex, 1)
  }
}

// Ref image upload
const refFileInputRefs = ref({})
const subjectFileInputRefs = ref({})
const uploadingRefIndex = ref(null)

function triggerRefFileInput(index) {
  refFileInputRefs.value[index]?.click()
}

function setRefFileInput(index, el) {
  if (el) refFileInputRefs.value[index] = el
  else delete refFileInputRefs.value[index]
}

function triggerSubjectFileInput(index, imgIdx) {
  subjectFileInputRefs.value[`${index}_${imgIdx}`]?.click()
}

function setSubjectFileInput(index, imgIdx, el) {
  const key = `${index}_${imgIdx}`
  if (el) subjectFileInputRefs.value[key] = el
  else delete subjectFileInputRefs.value[key]
}

// Upload a picked file into the project and point `target.url` (a ref, or
// one of a subject ref's images) at it. `busyKey` drives that row's spinner.
async function handleRefFileUpload(event, target, busyKey, label = 'Ref image') {
  const file = event.target.files?.[0]
  if (!file) return
  event.target.value = ''

  uploadingRefIndex.value = busyKey
  try {
    const result = await uploadRefImage(props.project, file)
    target.url = result.image_url  // "local:ref-abc123.jpg"
    showToast(`${label} uploaded`, 'success')
  } catch (err) {
    showToast('Upload failed: ' + err.message, 'error')
  } finally {
    uploadingRefIndex.value = null
  }
}

function removeRefLocalImage(refItem) {
  refItem.url = ''
}

// Initialize refs with one empty ref when switching to ref mode
watch(showRefFields, (show) => {
  if (show && settings.value.refs.length === 0) {
    addRef()
  }
})

async function handleSubmit() {
  if (!prompt.value.trim()) {
    showToast('Prompt is required', 'error')
    return
  }

  isSubmitting.value = true
  saveSettings()

  const data = {
    model: settings.value.model,
    project: props.project,
    prompt: prompt.value,
    image_url: settings.value.image_url,
    aspect_ratio: settings.value.aspect_ratio,
    length: settings.value.length,
    resolution: settings.value.resolution,
    generate_audio: settings.value.generate_audio,
    web_search: settings.value.web_search,
    image_tail: settings.value.image_tail,
  }

  // Seed (optional number)
  if (showSeedOption.value && settings.value.seed) {
    data.seed = parseInt(settings.value.seed, 10) || undefined
  }

  // Max images (optional, 1–4)
  if (showMaxImagesOption.value && settings.value.max_images) {
    const n = parseInt(settings.value.max_images, 10)
    if (n >= 1 && n <= 4) data.max_images = n
  }

  if (showThinkingLevelOption.value) {
    data.thinking_level = settings.value.thinking_level
  }

  if (inV1RefMode.value) {
    // v1 refs are just { type, url } — no names, order or subjects
    const info = refModeInfo.value
    const validRefs = settings.value.refs
      .filter(r => r.url && r.url.trim())
      .map(r => ({ type: r.type, url: r.url.trim() }))
    const counts = {}
    validRefs.forEach(r => { counts[r.type] = (counts[r.type] || 0) + 1 })
    const error = (() => {
      if (!validRefs.some(r => r.type !== 'audio')) return 'At least one non-audio reference is required'
      const badType = validRefs.find(r => !info.types.includes(r.type))
      if (badType) return `This model doesn't accept ${REF_TYPE_LABELS[badType.type] || badType.type} references`
      if (validRefs.length > info.max) return `Too many references (max ${info.max})`
      for (const [type, limit] of Object.entries(info.limits || {})) {
        if ((counts[type] || 0) > limit) return `Too many ${REF_TYPE_LABELS[type]} references (max ${limit})`
      }
      if ((info.exclusive || []).filter(t => counts[t]).length > 1) {
        return `Can't combine ${info.exclusive.map(t => REF_TYPE_LABELS[t]).join(' and ')} references`
      }
      if (info.max_length_with_video && counts.video && settings.value.length > info.max_length_with_video) {
        return `Length must be ${info.max_length_with_video}s or less with a video reference`
      }
      return null
    })()
    if (error) {
      showToast(error, 'error')
      isSubmitting.value = false
      return
    }
    data.refs = validRefs
    delete data.image_url
    delete data.image_tail
  } else if (showRefFields.value) {
    // Build refs payload per type
    let order = 1
    const validRefs = []
    for (const r of settings.value.refs) {
      const name = (r.name || `ref${validRefs.length + 1}`).slice(0, 20)
      if (r.type === 'subject') {
        const urls = (r.images || []).filter(img => img.url && img.url.trim()).map(img => ({ url: img.url.trim() }))
        if (urls.length === 0) continue
        validRefs.push({ type: 'subject', name, images: urls, subjectId: r.subjectId || '' })
      } else if (r.type === 'video') {
        if (!r.url || !r.url.trim()) continue
        validRefs.push({ type: 'video', name, video: r.url.trim(), order: order++ })
      } else if (r.type === 'audio') {
        if (!r.url || !r.url.trim()) continue
        validRefs.push({ type: 'audio', name, audio: r.url.trim(), order: order++ })
      } else {
        // image (default)
        if (!r.url || !r.url.trim()) continue
        validRefs.push({ type: 'image', name, image: r.url.trim(), order: order++ })
      }
    }
    if (validRefs.length === 0) {
      showToast('At least one reference is required', 'error')
      isSubmitting.value = false
      return
    }
    data.refs = validRefs
    if (settings.value.video_num > 1) {
      data.video_num = settings.value.video_num
    }
    // Ref models don't use source image
    delete data.image_url
  }

  try {
    // Show "Uploading image..." if using a local source image or local ref images
    const hasLocalSource = data.image_url && data.image_url.startsWith('local:')
    const hasLocalRefs = (data.refs || []).some(r => {
      if (r.type === 'image' && (r.image || r.url || '').startsWith('local:')) return true
      if (r.type === 'subject' && r.images) return r.images.some(img => img.url && img.url.startsWith('local:'))
      return false
    })
    if (hasLocalSource || hasLocalRefs) {
      submitStatus.value = 'uploading'
    } else {
      submitStatus.value = 'starting'
    }

    const result = await (modelType.value === 'image' ? generateImage(data) : generateVideo(data))

    // Add to global jobs queue
    addJob(result.job_id, settings.value.model, prompt.value, props.project)
    showToast('Generation started!', 'success')
  } catch (err) {
    showToast('Request failed: ' + (err.message || String(err)), 'error')
  } finally {
    isSubmitting.value = false
    submitStatus.value = ''
  }
}
</script>

<template>
  <div class="generate-panel">
    <form @submit.prevent="handleSubmit">
      <!-- Prompt -->
      <div class="form-section">
        <SleekTextarea
          v-model="prompt"
          label="Prompt"
          placeholder="Describe what you want to generate..."
          :rows="4"
        />
      </div>

      <!-- Legacy mode toggle -->
      <div class="form-section legacy-mode-row">
        <ToggleSwitch
          id="legacy_mode"
          :model-value="legacyMode"
          label="Legacy mode"
          @update:model-value="$emit('update:legacy-mode', $event)"
        />
        <span class="legacy-mode-hint">
          {{ legacyMode ? 'Showing old (pre-v1) API models' : 'Showing current (v1) API models' }}
        </span>
        <ToggleSwitch
          v-if="hiddenModelCount"
          id="show_hidden_models"
          v-model="showHidden"
          :label="`Show hidden (${hiddenModelCount})`"
          title="Models not enabled for this API key"
        />
      </div>

      <!-- Source Image & Model Row -->
      <div class="form-section">
        <div class="form-row source-row">
          <div v-if="!showRefFields" class="image-input-group flex2">
            <!-- Uploaded local image preview -->
            <div v-if="sourceImagePreviewUrl" class="source-preview">
              <img :src="sourceImagePreviewUrl" alt="Source" class="source-thumb" />
              <div class="source-preview-info">
                <span class="source-label">Uploaded image</span>
                <div class="source-actions">
                  <button type="button" class="btn-change" @click="triggerFileInput" :disabled="isUploading">Change</button>
                  <button type="button" class="btn-remove" @click="removeSourceImage">✕</button>
                </div>
              </div>
            </div>
            <!-- URL input + upload button when no local image -->
            <div v-else class="url-row">
              <SleekInput
                v-model="settings.image_url"
                label="Source Image"
                hint="optional"
                type="url"
                placeholder="https://example.com/image.jpg"
              />
              <button
                type="button"
                class="btn-upload"
                :disabled="isUploading"
                @click="triggerFileInput"
                :title="isUploading ? 'Uploading...' : 'Upload local image'"
              >
                <span v-if="isUploading" class="btn-spinner"></span>
                <span v-else>📁</span>
              </button>
            </div>
            <input
              ref="fileInputRef"
              type="file"
              accept="image/jpeg,image/png,image/webp,image/gif"
              style="display: none"
              @change="handleFileUpload"
            />
          </div>
          <SleekSelect
            v-model="settings.model"
            label="Model"
            :options="modelSelectOptions"
          />
        </div>
      </div>

      <!-- Video Settings Row -->
      <div class="form-section settings-row">
        <div class="setting-group" v-if="modelRatios.length > 0">
          <label>Aspect</label>
          <RatioPicker
            v-model="settings.aspect_ratio"
            :ratios="modelRatios"
          />
        </div>

        <LengthSlider
          v-if="modelLengths.length > 0"
          v-model="settings.length"
          :lengths="modelLengths"
        />

        <SleekSelect
          v-if="showResolution"
          v-model="settings.resolution"
          label="Resolution"
          :options="resolutions"
          class="compact"
        />

        <SleekInput
          v-if="showMaxImagesOption"
          v-model="settings.max_images"
          label="Images"
          hint="1–4"
          type="number"
          placeholder="1"
          class="compact"
        />

        <SleekSelect
          v-if="showThinkingLevelOption"
          v-model="settings.thinking_level"
          label="Thinking"
          :options="[{ value: 'minimal', label: 'Minimal' }, { value: 'high', label: 'High' }]"
          class="compact"
        />

        <!-- Toggles inline -->
        <div v-if="showAudioOption || showWebSearchOption || refModeInfo" class="toggle-group">
          <ToggleSwitch
            v-if="refModeInfo"
            id="ref_mode"
            v-model="settings.ref_mode"
            label="Refs"
            title="Reference mode: generate from reference images/videos/audio instead of a source image"
          />
          <ToggleSwitch
            v-if="showAudioOption"
            id="generate_audio"
            v-model="settings.generate_audio"
            label="Audio"
          />
          <ToggleSwitch
            v-if="showWebSearchOption"
            id="web_search"
            v-model="settings.web_search"
            label="Web"
          />
        </div>
      </div>

      <!-- End Frame (if available) -->
      <div v-if="showImageTailOption" class="form-section">
        <SleekInput
          v-model="settings.image_tail"
          label="End Frame URL"
          hint="optional - last frame image"
          type="url"
          placeholder="https://..."
        />
      </div>

      <!-- Seed (if available) -->
      <div v-if="showSeedOption" class="form-section">
        <SleekInput
          v-model="settings.seed"
          label="Seed"
          hint="optional - for reproducibility"
          type="number"
          placeholder="Random"
        />
      </div>

      <!-- Ref Fields -->
      <div v-if="showRefFields" class="form-section ref2-fields">
        <div class="ref2-header">
          <span class="ref2-title">References</span>
          <span class="ref2-hint">{{ settings.refs.length }}/{{ maxRefs }} refs</span>
        </div>

        <div
          v-for="(refItem, index) in settings.refs"
          :key="index"
          class="ref-item"
        >
          <div class="ref-item-header">
            <SleekSelect
              v-model="refItem.type"
              label="Type"
              :options="refTypes"
              class="ref-type"
              @update:modelValue="onRefTypeChange(index)"
            />
            <SleekInput
              v-if="!inV1RefMode"
              v-model="refItem.name"
              label="Name"
              :placeholder="`ref${index + 1}`"
              class="ref-name"
            />
            <button
              type="button"
              class="btn-remove-ref"
              @click="removeRef(index)"
              title="Remove"
            >✕</button>
          </div>

          <!-- Image / Video / Audio: single URL -->
          <div v-if="refItem.type === 'image'" class="ref-item-body">
            <!-- Local image preview -->
            <div v-if="previewUrl(refItem.url)" class="ref-preview">
              <img :src="previewUrl(refItem.url)" alt="Ref" class="ref-thumb" />
              <div class="ref-preview-info">
                <span class="source-label">Uploaded ref image</span>
                <div class="source-actions">
                  <button type="button" class="btn-change" @click="triggerRefFileInput(index)" :disabled="uploadingRefIndex === index">Change</button>
                  <button type="button" class="btn-remove" @click="removeRefLocalImage(refItem)">✕</button>
                </div>
              </div>
            </div>
            <!-- URL input + upload button -->
            <div v-else class="url-row">
              <SleekInput
                v-model="refItem.url"
                label="Image URL"
                type="url"
                placeholder="https://example.com/reference.jpg"
                class="ref-url-full"
              />
              <button
                type="button"
                class="btn-upload"
                :disabled="uploadingRefIndex === index"
                @click="triggerRefFileInput(index)"
                :title="uploadingRefIndex === index ? 'Uploading...' : 'Upload local image'"
              >
                <span v-if="uploadingRefIndex === index" class="btn-spinner"></span>
                <span v-else>📁</span>
              </button>
            </div>
            <input
              :ref="(el) => setRefFileInput(index, el)"
              type="file"
              accept="image/jpeg,image/png,image/webp,image/gif"
              style="display: none"
              @change="handleRefFileUpload($event, refItem, index)"
            />
          </div>

          <div v-else-if="refItem.type === 'video'" class="ref-item-body">
            <SleekInput
              v-model="refItem.url"
              label="Video URL"
              type="url"
              placeholder="https://example.com/reference.mp4"
              class="ref-url-full"
            />
          </div>

          <div v-else-if="refItem.type === 'audio'" class="ref-item-body">
            <SleekInput
              v-model="refItem.url"
              label="Audio URL"
              type="url"
              placeholder="https://example.com/audio.mp3"
              class="ref-url-full"
            />
          </div>

          <div v-else-if="refItem.type === 'file' || refItem.type === 'link'" class="ref-item-body">
            <SleekInput
              v-model="refItem.url"
              :label="`${REF_TYPE_LABELS[refItem.type]} URL`"
              type="url"
              :placeholder="REF_URL_PLACEHOLDERS[refItem.type]"
              class="ref-url-full"
            />
          </div>

          <!-- Subject: multiple images + subjectId -->
          <div v-else-if="refItem.type === 'subject'" class="ref-item-body subject-body">
            <SleekInput
              v-model="refItem.subjectId"
              label="Subject ID"
              placeholder="e.g. character-001"
              class="subject-id"
            />
            <div class="subject-images">
              <div
                v-for="(img, imgIdx) in refItem.images"
                :key="imgIdx"
                class="subject-image-row"
              >
                <!-- Local image preview for subject -->
                <div v-if="previewUrl(img.url)" class="ref-preview ref-preview-inline">
                  <img :src="previewUrl(img.url)" alt="Subject" class="ref-thumb-small" />
                  <span class="source-label">Uploaded</span>
                  <button type="button" class="btn-remove" @click="img.url = ''">✕</button>
                </div>
                <template v-else>
                  <SleekInput
                    v-model="img.url"
                    :label="`Image ${imgIdx + 1}`"
                    type="url"
                    placeholder="https://example.com/subject.jpg"
                    class="ref-url-full"
                  />
                  <button
                    type="button"
                    class="btn-upload btn-upload-small"
                    :disabled="uploadingRefIndex === `subject-${imgIdx}`"
                    @click="triggerSubjectFileInput(index, imgIdx)"
                    title="Upload local image"
                  >
                    <span v-if="uploadingRefIndex === `subject-${imgIdx}`" class="btn-spinner"></span>
                    <span v-else>📁</span>
                  </button>
                </template>
                <input
                  :ref="(el) => setSubjectFileInput(index, imgIdx, el)"
                  type="file"
                  accept="image/jpeg,image/png,image/webp,image/gif"
                  style="display: none"
                  @change="handleRefFileUpload($event, img, `subject-${imgIdx}`, 'Subject image')"
                />
                <button
                  v-if="refItem.images.length > 1"
                  type="button"
                  class="btn-remove-ref btn-remove-small"
                  @click="removeSubjectImage(refItem, imgIdx)"
                  title="Remove image"
                >✕</button>
              </div>
              <button
                v-if="refItem.images.length < 3"
                type="button"
                class="btn-add-subject-img"
                @click="addSubjectImage(refItem)"
              >+ Add Image ({{ refItem.images.length }}/3)</button>
            </div>
          </div>
        </div>

        <button
          type="button"
          class="btn-add-ref"
          :disabled="settings.refs.length >= maxRefs"
          @click="addRef"
        >
          + Add Reference
        </button>

        <!-- Video Count -->
        <div v-if="showVideoNumOption" class="ref2-options">
          <div class="video-num-control">
            <label>Videos to generate</label>
            <div class="video-num-buttons">
              <button
                v-for="n in 4"
                :key="n"
                type="button"
                :class="['num-btn', { active: settings.video_num === n }]"
                @click="settings.video_num = n"
              >{{ n }}</button>
            </div>
          </div>
        </div>
      </div>

      <div v-if="isDeprecatedModel" class="deprecated-warning">
        ⚠️ This model's API endpoint has been removed and generation will likely fail. Are you sure?
      </div>

      <div class="actions">
        <button type="submit" :class="['btn', isDeprecatedModel ? 'btn-deprecated' : 'btn-primary']" :disabled="isSubmitting">
          <span v-if="isSubmitting" class="btn-spinner"></span>
          {{ submitButtonText }}
        </button>
      </div>
    </form>
  </div>
</template>

<style scoped>
.form-section {
  margin-bottom: 20px;
}

.form-row {
  display: flex;
  gap: 16px;
  flex-wrap: wrap;
  align-items: flex-end;
}

.source-row {
  flex-wrap: nowrap;
}

.source-row :deep(.flex2) {
  flex: 2;
  min-width: 200px;
}

.image-input-group {
  flex: 2;
  min-width: 200px;
}

.url-row {
  display: flex;
  gap: 8px;
  align-items: flex-end;
}

.url-row :deep(.sleek-input) {
  flex: 1;
}

.btn-upload {
  background: linear-gradient(145deg, rgba(30, 30, 35, 0.9), rgba(25, 25, 30, 0.95));
  border: 1px solid rgba(255, 255, 255, 0.06);
  border-radius: 10px;
  width: 42px;
  height: 42px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 1.1rem;
  flex-shrink: 0;
  margin-bottom: 8px;
  transition: all 0.2s;
}

.btn-upload:hover:not(:disabled) {
  border-color: rgba(108, 92, 231, 0.4);
  background: linear-gradient(145deg, rgba(35, 32, 45, 0.95), rgba(28, 26, 38, 0.98));
  box-shadow: 0 0 0 3px rgba(108, 92, 231, 0.1);
}

.btn-upload:disabled {
  opacity: 0.5;
  cursor: wait;
}

.source-preview {
  display: flex;
  gap: 12px;
  align-items: center;
  padding: 8px 12px;
  background: linear-gradient(145deg, rgba(30, 30, 35, 0.9), rgba(25, 25, 30, 0.95));
  border: 1px solid rgba(255, 255, 255, 0.06);
  border-radius: 10px;
  margin-bottom: 8px;
}

.source-thumb {
  width: 48px;
  height: 48px;
  object-fit: cover;
  border-radius: 8px;
  flex-shrink: 0;
}

.source-preview-info {
  display: flex;
  flex-direction: column;
  gap: 4px;
  flex: 1;
  min-width: 0;
}

.source-label {
  font-size: 0.75rem;
  color: var(--text2);
  font-weight: 500;
}

.source-actions {
  display: flex;
  gap: 6px;
}

.btn-change {
  background: rgba(108, 92, 231, 0.1);
  border: 1px solid rgba(108, 92, 231, 0.2);
  color: rgba(108, 92, 231, 0.9);
  border-radius: 6px;
  padding: 3px 10px;
  cursor: pointer;
  font-size: 0.7rem;
  font-weight: 500;
  transition: all 0.2s;
}

.btn-change:hover:not(:disabled) {
  background: rgba(108, 92, 231, 0.2);
}

.btn-remove {
  background: rgba(255, 60, 60, 0.1);
  border: 1px solid rgba(255, 60, 60, 0.15);
  color: rgba(255, 100, 100, 0.8);
  border-radius: 6px;
  width: 24px;
  height: 24px;
  cursor: pointer;
  font-size: 0.7rem;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s;
}

.btn-remove:hover {
  background: rgba(255, 60, 60, 0.2);
}

.settings-row {
  display: flex;
  gap: 20px;
  flex-wrap: wrap;
  align-items: center;
  padding: 16px 20px 28px;
  background: linear-gradient(145deg, rgba(22, 22, 28, 0.95), rgba(18, 18, 22, 0.98));
  border-radius: 14px;
  border: 1px solid rgba(255, 255, 255, 0.04);
  box-shadow:
    inset 0 1px 1px rgba(255, 255, 255, 0.02),
    0 4px 20px rgba(0, 0, 0, 0.15);
}

.setting-group {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.setting-group label {
  font-size: 0.72rem;
  font-weight: 600;
  color: var(--text2);
  text-transform: uppercase;
  letter-spacing: 0.08em;
}

.toggle-group {
  display: flex;
  gap: 16px;
  margin-left: auto;
  padding-left: 20px;
  border-left: 1px solid rgba(255, 255, 255, 0.06);
}

.legacy-mode-row {
  display: flex;
  align-items: center;
  gap: 10px;
}

.legacy-mode-hint {
  font-size: 0.78rem;
  color: var(--text2);
}

.settings-row :deep(.compact) {
  min-width: 100px;
  width: 100px;
  margin-bottom: 0;
}

/* --- Ref --- */
.ref2-fields {
  padding: 16px 20px;
  background: linear-gradient(145deg, rgba(22, 22, 28, 0.95), rgba(18, 18, 22, 0.98));
  border-radius: 14px;
  border: 1px solid rgba(255, 255, 255, 0.04);
  box-shadow:
    inset 0 1px 1px rgba(255, 255, 255, 0.02),
    0 4px 20px rgba(0, 0, 0, 0.15);
}

.ref2-header {
  display: flex;
  align-items: baseline;
  gap: 10px;
  margin-bottom: 12px;
}

.ref2-title {
  font-size: 0.72rem;
  font-weight: 600;
  color: var(--text2);
  text-transform: uppercase;
  letter-spacing: 0.08em;
}

.ref2-hint {
  font-size: 0.68rem;
  color: var(--text2);
  opacity: 0.5;
  font-weight: 400;
}

.ref-item {
  margin-bottom: 12px;
  padding: 10px 12px;
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.02);
  border: 1px solid rgba(255, 255, 255, 0.04);
}

.ref-item-header {
  display: flex;
  gap: 10px;
  align-items: flex-end;
  margin-bottom: 8px;
}

.ref-item-header :deep(.ref-type) {
  width: 110px;
  min-width: 100px;
  flex-shrink: 0;
}

.ref-item-header :deep(.ref-name) {
  width: 130px;
  min-width: 100px;
  flex-shrink: 0;
}

.ref-item-body {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.ref-item-body :deep(.ref-url-full) {
  flex: 1;
}

.ref-preview {
  display: flex;
  gap: 12px;
  align-items: center;
  padding: 8px 12px;
  background: linear-gradient(145deg, rgba(30, 30, 35, 0.9), rgba(25, 25, 30, 0.95));
  border: 1px solid rgba(255, 255, 255, 0.06);
  border-radius: 10px;
}

.ref-preview-inline {
  gap: 8px;
  padding: 6px 10px;
}

.ref-thumb {
  width: 48px;
  height: 48px;
  object-fit: cover;
  border-radius: 8px;
  flex-shrink: 0;
}

.ref-thumb-small {
  width: 32px;
  height: 32px;
  object-fit: cover;
  border-radius: 6px;
  flex-shrink: 0;
}

.ref-preview-info {
  display: flex;
  flex-direction: column;
  gap: 4px;
  flex: 1;
  min-width: 0;
}

.btn-upload-small {
  width: 36px;
  height: 36px;
  font-size: 0.95rem;
}

.subject-body {
  gap: 10px;
}

.subject-body :deep(.subject-id) {
  max-width: 220px;
}

.subject-images {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.subject-image-row {
  display: flex;
  gap: 8px;
  align-items: flex-end;
}

.subject-image-row :deep(.ref-url-full) {
  flex: 1;
}

.btn-remove-small {
  width: 30px;
  height: 30px;
  font-size: 0.75rem;
}

.btn-add-subject-img {
  background: rgba(108, 92, 231, 0.06);
  border: 1px dashed rgba(108, 92, 231, 0.2);
  color: rgba(108, 92, 231, 0.7);
  border-radius: 8px;
  padding: 6px 14px;
  cursor: pointer;
  font-size: 0.75rem;
  font-weight: 500;
  width: fit-content;
  transition: all 0.2s;
}

.btn-add-subject-img:hover {
  background: rgba(108, 92, 231, 0.12);
  border-color: rgba(108, 92, 231, 0.4);
}

.btn-remove-ref {
  background: rgba(255, 60, 60, 0.12);
  border: 1px solid rgba(255, 60, 60, 0.2);
  color: rgba(255, 100, 100, 0.8);
  border-radius: 8px;
  width: 36px;
  height: 36px;
  cursor: pointer;
  font-size: 0.85rem;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  margin-bottom: 8px;
  transition: all 0.2s;
}

.btn-remove-ref:hover {
  background: rgba(255, 60, 60, 0.22);
  border-color: rgba(255, 60, 60, 0.4);
}

.btn-add-ref {
  background: rgba(108, 92, 231, 0.08);
  border: 1px dashed rgba(108, 92, 231, 0.3);
  color: rgba(108, 92, 231, 0.8);
  border-radius: 10px;
  padding: 10px 18px;
  cursor: pointer;
  font-size: 0.82rem;
  font-weight: 500;
  width: 100%;
  margin-top: 4px;
  transition: all 0.2s;
}

.btn-add-ref:hover:not(:disabled) {
  background: rgba(108, 92, 231, 0.15);
  border-color: rgba(108, 92, 231, 0.5);
}

.btn-add-ref:disabled {
  opacity: 0.35;
  cursor: not-allowed;
}

.ref2-options {
  margin-top: 16px;
  padding-top: 14px;
  border-top: 1px solid rgba(255, 255, 255, 0.06);
}

.video-num-control {
  display: flex;
  align-items: center;
  gap: 12px;
}

.video-num-control label {
  font-size: 0.72rem;
  font-weight: 600;
  color: var(--text2);
  text-transform: uppercase;
  letter-spacing: 0.08em;
  white-space: nowrap;
}

.video-num-buttons {
  display: flex;
  gap: 6px;
}

.num-btn {
  width: 36px;
  height: 32px;
  border-radius: 8px;
  border: 1px solid rgba(255, 255, 255, 0.08);
  background: rgba(30, 30, 35, 0.8);
  color: var(--text2);
  font-size: 0.85rem;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
}

.num-btn:hover {
  border-color: rgba(108, 92, 231, 0.3);
  color: var(--text);
}

.num-btn.active {
  background: rgba(108, 92, 231, 0.2);
  border-color: rgba(108, 92, 231, 0.5);
  color: var(--accent2);
  font-weight: 600;
}

.deprecated-warning {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 14px;
  margin-top: 16px;
  background: rgba(245, 158, 11, 0.08);
  border: 1px solid rgba(245, 158, 11, 0.25);
  border-radius: 10px;
  font-size: 0.8rem;
  color: rgba(251, 191, 36, 0.9);
  line-height: 1.4;
}

.actions {
  display: flex;
  gap: 12px;
  margin-top: 16px;
  justify-content: flex-end;
}

.btn-deprecated {
  background: linear-gradient(135deg, rgba(180, 110, 0, 0.7), rgba(160, 90, 0, 0.8));
  border: 1px solid rgba(245, 158, 11, 0.4);
  color: rgba(251, 191, 36, 0.95);
  box-shadow: 0 0 0 0 rgba(245, 158, 11, 0);
  transition: all 0.2s;
}

.btn-deprecated:hover:not(:disabled) {
  background: linear-gradient(135deg, rgba(200, 130, 0, 0.8), rgba(180, 110, 0, 0.9));
  border-color: rgba(245, 158, 11, 0.6);
  box-shadow: 0 0 12px rgba(245, 158, 11, 0.2);
}
</style>


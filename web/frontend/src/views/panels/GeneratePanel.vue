<script setup>
import { ref, computed, watch, inject } from 'vue'
import { RatioPicker, LengthSlider, ToggleSwitch, SleekTextarea, SleekSelect, SleekInput } from '../../components/form'
import { generateVideo, uploadSourceImage, deleteSourceImage, getSourceImageUrl, uploadRefImage, getRefImageUrl } from '../../composables/useApi'
import { useProjectSettings } from '../../composables/useProjectSettings'
import { useJobsQueue } from '../../composables/useJobsQueue'

const props = defineProps({
  project: { type: String, required: true },
  projectData: { type: Object, default: null },
  models: { type: Object, default: () => ({}) },
  regenerateJob: { type: Object, default: null },
  useAsRef: { type: Object, default: null }
})

const emit = defineEmits(['regenerate-applied', 'use-as-ref-applied'])

const showToast = inject('showToast')
const { addJob } = useJobsQueue()

// Form state
const projectRef = computed(() => props.project)
const { settings, save: saveSettings, applyProjectData, applyJobSettings } = useProjectSettings(projectRef)

const prompt = ref('')
const isSubmitting = ref(false)
const submitStatus = ref('')  // '', 'uploading', 'starting'
const submitButtonText = computed(() => {
  if (submitStatus.value === 'uploading') return 'Uploading'
  if (submitStatus.value === 'starting') return 'Starting'
  return '🚀 Generate'
})

// Model options
const selectedModel = computed(() => props.models[settings.value.model] || {})
const modelType = computed(() => selectedModel.value.type || 'img2vid')
const modelLengths = computed(() => selectedModel.value.lengths || [5, 10])
const modelRatios = computed(() => selectedModel.value.ratios || ['9:16', '16:9'])
const modelOptions = computed(() => selectedModel.value.options || [])

const showAudioOption = computed(() => modelOptions.value.includes('generate_audio'))
const showWebSearchOption = computed(() => modelOptions.value.includes('web_search'))
const showImageTailOption = computed(() => modelOptions.value.includes('image_tail'))
const showSeedOption = computed(() => modelOptions.value.includes('seed'))
const showRefFields = computed(() => modelType.value === 'ref')
const showVideoNumOption = computed(() => modelOptions.value.includes('video_num'))

const resolutions = ['480p', '720p', '1080p']

// Source image upload
const isUploading = ref(false)
const fileInputRef = ref(null)
const hasLocalImage = computed(() => (settings.value.image_url || '').startsWith('local:'))
const localImageFilename = computed(() => {
  const url = settings.value.image_url || ''
  return url.startsWith('local:') ? url.slice(6) : ''
})
const sourceImagePreviewUrl = computed(() => {
  if (!hasLocalImage.value) return null
  return getSourceImageUrl(props.project) + '?f=' + encodeURIComponent(localImageFilename.value)
})

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
    await deleteSourceImage(props.project, localImageFilename.value)
    settings.value.image_url = ''
    showToast('Source image removed', 'success')
  } catch (err) {
    showToast('Failed to remove: ' + err.message, 'error')
  }
}

// Format models for SleekSelect
const modelSelectOptions = computed(() => {
  return Object.entries(props.models).map(([key, info]) => ({
    value: key,
    label: `${info.label}${info.type === 'ref' ? ' (ref)' : ''}`
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
    emit('regenerate-applied')
    showToast('Settings loaded from video', 'success')
  }
}, { immediate: true })

// Watch for use-as-ref - switch to ref model and prefill refs
watch(() => props.useAsRef, (data) => {
  if (data) {
    settings.value.model = 'pollodanceref'
    settings.value.refs = data.refs || []
    if (data.prompt) {
      prompt.value = data.prompt
    }
    emit('use-as-ref-applied')
    showToast('Video added as reference', 'success')
  }
}, { immediate: true })

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

// --- Refs management for ref2video ---
const refTypes = [
  { value: 'image', label: 'Image' },
  { value: 'subject', label: 'Subject' },
  { value: 'video', label: 'Video' },
  { value: 'audio', label: 'Audio' },
]

function newRefItem(type = 'image') {
  const order = settings.value.refs.length + 1
  if (type === 'subject') {
    return { type: 'subject', name: '', images: [{ url: '' }], subjectId: '' }
  }
  // image, video, audio all share the same shape: url + order
  return { type, name: '', url: '', order }
}

function addRef() {
  if (settings.value.refs.length >= 13) return
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
const uploadingRefIndex = ref(null)

function triggerRefFileInput(index) {
  const input = refFileInputRefs.value[index]
  if (input) input.click()
}

function setRefFileInput(index, el) {
  if (el) refFileInputRefs.value[index] = el
}

async function handleRefFileUpload(event, index) {
  const file = event.target.files?.[0]
  if (!file) return
  event.target.value = ''

  uploadingRefIndex.value = index
  try {
    const result = await uploadRefImage(props.project, file)
    settings.value.refs[index].url = result.image_url  // "local:ref-abc123.jpg"
    showToast('Ref image uploaded', 'success')
  } catch (err) {
    showToast('Upload failed: ' + err.message, 'error')
  } finally {
    uploadingRefIndex.value = null
  }
}

async function handleSubjectRefFileUpload(event, refItem, imgIndex) {
  const file = event.target.files?.[0]
  if (!file) return
  event.target.value = ''

  uploadingRefIndex.value = `subject-${imgIndex}`
  try {
    const result = await uploadRefImage(props.project, file)
    refItem.images[imgIndex].url = result.image_url
    showToast('Subject image uploaded', 'success')
  } catch (err) {
    showToast('Upload failed: ' + err.message, 'error')
  } finally {
    uploadingRefIndex.value = null
  }
}

function getRefPreviewUrl(refItem) {
  const url = refItem.url || ''
  if (!url.startsWith('local:')) return null
  return getRefImageUrl(props.project, url.slice(6))
}

function getSubjectImagePreviewUrl(img) {
  const url = img.url || ''
  if (!url.startsWith('local:')) return null
  return getRefImageUrl(props.project, url.slice(6))
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

  if (showRefFields.value) {
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
      if (r.type === 'image' && r.image && r.image.startsWith('local:')) return true
      if (r.type === 'subject' && r.images) return r.images.some(img => img.url && img.url.startsWith('local:'))
      return false
    })
    if (hasLocalSource || hasLocalRefs) {
      submitStatus.value = 'uploading'
    } else {
      submitStatus.value = 'starting'
    }

    const result = await generateVideo(data)

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

      <!-- Source Image & Model Row -->
      <div class="form-section">
        <div class="form-row source-row">
          <div v-if="!showRefFields" class="image-input-group flex2">
            <!-- Uploaded local image preview -->
            <div v-if="hasLocalImage" class="source-preview">
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
        <div class="setting-group">
          <label>Aspect</label>
          <RatioPicker
            v-model="settings.aspect_ratio"
            :ratios="modelRatios"
          />
        </div>

        <LengthSlider
          v-model="settings.length"
          :lengths="modelLengths"
        />

        <SleekSelect
          v-model="settings.resolution"
          label="Resolution"
          :options="resolutions"
          class="compact"
        />

        <!-- Toggles inline -->
        <div v-if="showAudioOption || showWebSearchOption" class="toggle-group">
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
          <span class="ref2-hint">{{ settings.refs.length }}/13 refs</span>
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
            <div v-if="refItem.url && refItem.url.startsWith('local:')" class="ref-preview">
              <img :src="getRefPreviewUrl(refItem)" alt="Ref" class="ref-thumb" />
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
              @change="handleRefFileUpload($event, index)"
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
                <div v-if="img.url && img.url.startsWith('local:')" class="ref-preview ref-preview-inline">
                  <img :src="getSubjectImagePreviewUrl(img)" alt="Subject" class="ref-thumb-small" />
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
                    @click="$refs[`subjectFileInput_${index}_${imgIdx}`]?.[0]?.click()"
                    title="Upload local image"
                  >
                    <span v-if="uploadingRefIndex === `subject-${imgIdx}`" class="btn-spinner"></span>
                    <span v-else>📁</span>
                  </button>
                </template>
                <input
                  :ref="`subjectFileInput_${index}_${imgIdx}`"
                  type="file"
                  accept="image/jpeg,image/png,image/webp,image/gif"
                  style="display: none"
                  @change="handleSubjectRefFileUpload($event, refItem, imgIdx)"
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
          :disabled="settings.refs.length >= 13"
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

      <div class="actions">
        <button type="submit" class="btn btn-primary" :disabled="isSubmitting">
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
  align-items: flex-end;
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

.settings-row :deep(.compact) {
  min-width: 100px;
  width: 100px;
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

.actions {
  display: flex;
  gap: 12px;
  margin-top: 24px;
  justify-content: flex-end;
}
</style>


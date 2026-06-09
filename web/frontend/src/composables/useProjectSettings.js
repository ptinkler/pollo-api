import { ref, watch } from 'vue'

const STORAGE_PREFIX = 'pollo_settings_'

export function useProjectSettings(projectName) {
  const settings = ref({
    model: 'seedance20fast',
    aspect_ratio: '9:16',
    resolution: '480p',
    length: 10,
    generate_audio: false,
    web_search: false,
    image_url: '',
    image_tail: '',
    seed: '',
    refs: [],
    video_num: 1,
  })

  function load() {
    try {
      const stored = localStorage.getItem(STORAGE_PREFIX + projectName.value)
      if (stored) {
        const parsed = JSON.parse(stored)
        Object.assign(settings.value, parsed)
      }
    } catch (e) {
      console.warn('Failed to load settings:', e)
    }
  }

  function save() {
    try {
      localStorage.setItem(STORAGE_PREFIX + projectName.value, JSON.stringify(settings.value))
    } catch (e) {
      console.warn('Failed to save settings:', e)
    }
  }

  function applyProjectData(projectData) {
    // Apply URLs from project data if not already set locally
    for (const key of ['image_url']) {
      if (projectData[key] && !settings.value[key]) {
        settings.value[key] = projectData[key]
      }
    }
  }

  function applyJobSettings(job) {
    // Apply ALL settings from a job (for regenerate)
    // This does NOT save to localStorage - that only happens on generate
    if (job.model) settings.value.model = job.model
    if (job.aspect_ratio) settings.value.aspect_ratio = job.aspect_ratio
    if (job.resolution) settings.value.resolution = job.resolution
    if (job.length) settings.value.length = job.length
    
    // Boolean options - check for explicit true/false
    settings.value.generate_audio = !!job.generate_audio
    
    // Extra params stored in params object
    const params = job.params || {}
    settings.value.web_search = !!params.web_search
    settings.value.image_tail = params.image_tail || ''
    settings.value.seed = params.seed !== null && params.seed !== undefined ? String(params.seed) : ''
    settings.value.video_num = params.video_num || 1
    // Map stored ref format back to UI format (stored: image/video/audio key, UI: url key)
    settings.value.refs = (params.refs || []).map(r => {
      if (r.type === 'subject') {
        // For subject refs prefer the preserved local url if available
        const images = (r.images || []).map(img => {
          const local = img._local_url || img._local || null
          return { url: local || img.url || '' }
        })
        return { type: 'subject', name: r.name || '', images: images.length ? images : [{ url: '' }], subjectId: r.subjectId || '' }
      }
      // image, video, audio refs store URL under their type key; UI uses `url`
      // Prefer preserved local refs (_local_image / _local_url) when present
      const url = r._local_image || r._local_url || r.url || r.image || r.video || r.audio || ''
      return { type: r.type || 'image', name: r.name || '', url, order: r.order || 0 }
    })

    // Prefer the recorded local reference (if present in job params) so the
    // regenerate Source Image input shows the permanent local file instead
    // of the temporary uploaded URL.
    if (params.source_local) {
      settings.value.image_url = params.source_local
    } else {
      settings.value.image_url = job.image_url || ''
    }
  }

  // Load on project change
  watch(projectName, () => {
    if (projectName.value) {
      load()
    }
  }, { immediate: true })

  return { settings, load, save, applyProjectData, applyJobSettings }
}


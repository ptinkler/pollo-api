import { ref, watch } from 'vue'

const STORAGE_PREFIX = 'pollo_settings_'

// A stored ref in the form's shape: stored refs keep the URL under their
// type's key ("image", "video", "audio"), the form under `url`, and the
// local file a ref was uploaded from wins over the temporary upload
function refForForm(r) {
  const name = r.name || ''
  if (r.type !== 'subject') return { type: r.type || 'image', name, url: refUrl(r), order: r.order || 0 }
  const images = (r.images || []).map(img => ({ url: img._local_url || img._local || img.url || '' }))
  return { type: 'subject', name, images: images.length ? images : [{ url: '' }], subjectId: r.subjectId || '' }
}

const REF_URL_KEYS = ['_local_image', '_local_url', 'url', 'image', 'video', 'audio']
const refUrl = r => REF_URL_KEYS.map(key => r[key]).find(Boolean) || ''

export function useProjectSettings(projectName) {
  const settings = ref({
    model: 'seedance20fastv1',
    aspect_ratio: '9:16',
    resolution: '480p',
    length: 10,
    generate_audio: false,
    web_search: false,
    image_url: '',
    image_tail: '',
    seed: '',
    refs: [],
    ref_mode: false,
    video_num: 1,
    max_images: '1',
    thinking_level: 'minimal',
    character_ids: [],
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

  // Apply ALL settings from a job (for regenerate). Not saved to
  // localStorage — that only happens on generate.
  function applyJobSettings(job) {
    const params = job.params || {}
    const refs = params.refs || []
    const given = { model: job.model, aspect_ratio: job.aspect_ratio, resolution: job.resolution, length: job.length }
    for (const [key, value] of Object.entries(given)) {
      if (value) settings.value[key] = value
    }
    Object.assign(settings.value, {
      generate_audio: !!job.generate_audio,
      web_search: !!params.web_search,
      image_tail: params.image_tail || '',
      seed: params.seed != null ? String(params.seed) : '',
      video_num: params.video_num || 1,
      max_images: params.max_images ? String(params.max_images) : '',
      character_ids: params.character_ids || [],
      // Refs that came from characters are re-added from the characters themselves
      refs: refs.filter(r => !r._character).map(refForForm),
      // v1 models only take refs in ref mode, so a job that used refs was one
      ref_mode: refs.length > 0,
      // The recorded local file rather than the temporary upload, so the
      // Source Image input shows the permanent copy
      image_url: params.source_local || job.image_url || '',
    })
  }

  // Load on project change
  watch(
    projectName,
    () => {
      if (projectName.value) {
        load()
      }
    },
    { immediate: true },
  )

  return { settings, load, save, applyProjectData, applyJobSettings }
}

import { ref, reactive, computed, watch } from 'vue'

// The chat composer's settings: models, mode, the memory and image sliders
// and the media options. Remembered per browser (the last ones used) and per
// chat (restored when it's opened).

export const MODES = [
  { id: 'auto', label: 'Auto', icon: '✦', hint: 'Chat model decides when to make images or videos' },
  { id: 'text', label: 'Chat', icon: '💬', hint: 'Text replies only' },
  { id: 'image', label: 'Image', icon: '🖼', hint: 'Send the prompt straight to the image model' },
  { id: 'video', label: 'Video', icon: '🎬', hint: 'Send the prompt (and image) straight to the video model' },
]
const DEFAULT_RATIOS = ['1:1', '16:9', '9:16', '4:3', '3:4', '3:2', '2:3', '21:9']
// First id containing one of these wins when nothing is remembered yet
const PREFERRED = {
  text: ['anthropic/claude-sonnet', 'google/gemini', 'openai/gpt'],
  image: ['gemini', 'seedream', 'flux', 'gpt-image'],
  video: ['veo', 'seedance', 'wan', 'sora'],
}
const STORE_KEY = 'chat.prefs'
// Memory slider stops: how many past messages the chat model gets (null = all)
export const MEMORY_STEPS = [2, 4, 6, 10, 14, 20, 30, 40, 60, 80, 100, null]
const DEFAULT_MEMORY = 20
// Image slider stops: how many recent chat images go with each request (null = all)
export const IMAGE_STEPS = [0, 1, 2, 3, 4, 6, 8, 10, 12, 16, 20, null]
const DEFAULT_IMAGES = 6 // mirrors DEFAULT_IMAGE_LIMIT in web/chat.py

function loadPrefs() {
  try {
    return JSON.parse(localStorage.getItem(STORE_KEY)) || {}
  } catch {
    return {}
  }
}

// The slider stop for a remembered value, else for the default
function stepIndex(steps, prefs, key, fallback) {
  const i = steps.indexOf(key in prefs ? prefs[key] : fallback)
  return i === -1 ? steps.indexOf(fallback) : i
}

// Move a slider to a saved value's stop (null = "All"), if it's one of them
function setStep(index, steps, value) {
  const i = steps.indexOf(value ?? null)
  if (i !== -1) index.value = i
}

// Saved media options in the composer's shape: '' for unset
const optionsOrUnset = (saved, keys) => Object.fromEntries(keys.map(k => [k, saved?.[k] || '']))

const ratiosOf = info => (info?.aspect_ratios?.length ? info.aspect_ratios : DEFAULT_RATIOS)

// A newly picked model may not offer the old picks — fall back to auto/default
function dropUnsupported(opts, ratios, resolutions, durations = null) {
  if (opts.aspect_ratio && !ratios.includes(opts.aspect_ratio)) opts.aspect_ratio = ''
  if (opts.resolution && !resolutions.includes(opts.resolution)) opts.resolution = ''
  if (durations && opts.duration && !durations.includes(Number(opts.duration))) opts.duration = ''
}

/** `models`: the catalogues ({ text, image, video } lists) the pickers choose from. */
export function useComposerSettings(models) {
  const prefs = loadPrefs()
  const selected = reactive({ text: prefs.text || '', image: prefs.image ?? '', video: prefs.video ?? '' })
  const mode = ref(prefs.mode || 'auto')
  const memoryIndex = ref(stepIndex(MEMORY_STEPS, prefs, 'memory', DEFAULT_MEMORY))
  const imageIndex = ref(stepIndex(IMAGE_STEPS, prefs, 'images', DEFAULT_IMAGES))
  const historyLimit = computed(() => MEMORY_STEPS[memoryIndex.value])
  const imageLimit = computed(() => IMAGE_STEPS[imageIndex.value])
  // Settings for generated media, used in every mode (Auto too).
  // '' = let the chat model choose (Auto), else the media model's default.
  const imageOpts = reactive({ aspect_ratio: '', resolution: '', ...prefs.imageOpts })
  const videoOpts = reactive({
    aspect_ratio: '',
    resolution: '',
    duration: '',
    generate_audio: true,
    ...prefs.videoOpts,
  })

  watch(
    [() => ({ ...selected }), mode, memoryIndex, imageIndex, () => ({ ...imageOpts }), () => ({ ...videoOpts })],
    () => {
      try {
        localStorage.setItem(
          STORE_KEY,
          JSON.stringify({
            ...selected,
            mode: mode.value,
            memory: historyLimit.value,
            images: imageLimit.value,
            imageOpts: { ...imageOpts },
            videoOpts: { ...videoOpts },
          }),
        )
      } catch {
        /* storage unavailable */
      }
    },
    { deep: true },
  )

  const textInfo = computed(() => models.text.find(m => m.id === selected.text))
  const imageInfo = computed(() => models.image.find(m => m.id === selected.image))
  const videoInfo = computed(() => models.video.find(m => m.id === selected.video))
  const imageRatioOptions = computed(() => ratiosOf(imageInfo.value))
  const imageResOptions = computed(() => imageInfo.value?.resolutions || [])
  const videoRatioOptions = computed(() => ratiosOf(videoInfo.value))
  const videoResOptions = computed(() => videoInfo.value?.resolutions || [])
  const durationOptions = computed(() => videoInfo.value?.durations || [])
  const showImageOpts = computed(() => !!selected.image && ['auto', 'image'].includes(mode.value))
  const showVideoOpts = computed(() => !!selected.video && ['auto', 'video'].includes(mode.value))
  const currentMode = computed(() => MODES.find(m => m.id === mode.value) || MODES[0])

  watch(imageInfo, info => {
    if (info) dropUnsupported(imageOpts, imageRatioOptions.value, imageResOptions.value)
  })
  watch(videoInfo, info => {
    if (info) dropUnsupported(videoOpts, videoRatioOptions.value, videoResOptions.value, durationOptions.value)
  })

  function cycleMode() {
    const i = MODES.findIndex(m => m.id === mode.value)
    mode.value = MODES[(i + 1) % MODES.length].id
  }

  function pickDefault(kind) {
    const list = models[kind]
    if (!list.length) return ''
    const preferred = PREFERRED[kind]
      .map(needle => list.find(m => m.id.includes(needle) && (kind !== 'text' || m.supports_tools)))
      .find(Boolean)
    return (preferred || list[0]).id
  }

  // Once the catalogues are in: models for anything not picked yet. An empty
  // image/video pick is a deliberate "None" once the user has made one.
  function applyDefaults() {
    if (!selected.text) selected.text = pickDefault('text')
    if (!('image' in prefs)) selected.image = pickDefault('image')
    if (!('video' in prefs)) selected.video = pickDefault('video')
  }

  // A chat's own models and settings, restored when it's opened
  function applyChat(conv) {
    for (const kind of ['text', 'image', 'video']) {
      if (conv[`${kind}_model`]) selected[kind] = conv[`${kind}_model`]
    }
    const st = conv.settings
    if (!st) return
    if (MODES.some(m => m.id === st.mode)) mode.value = st.mode
    setStep(memoryIndex, MEMORY_STEPS, st.history_limit)
    setStep(imageIndex, IMAGE_STEPS, st.image_limit)
    Object.assign(imageOpts, optionsOrUnset(st.image_options, ['aspect_ratio', 'resolution']))
    Object.assign(videoOpts, optionsOrUnset(st.video_options, ['aspect_ratio', 'resolution', 'duration']))
    if (st.video_options?.generate_audio != null) videoOpts.generate_audio = st.video_options.generate_audio
  }

  // The settings a turn is sent with (retries and edits too: they run in the mode selected now)
  function turnSettings() {
    return {
      mode: mode.value,
      history_limit: historyLimit.value,
      image_limit: imageLimit.value,
      text_model: selected.text || null,
      image_model: selected.image || null,
      video_model: selected.video || null,
      image_options: { aspect_ratio: imageOpts.aspect_ratio || null, resolution: imageOpts.resolution || null },
      video_options: {
        aspect_ratio: videoOpts.aspect_ratio || null,
        resolution: videoOpts.resolution || null,
        duration: videoOpts.duration ? Number(videoOpts.duration) : null,
        generate_audio: videoInfo.value?.generate_audio ? videoOpts.generate_audio : null,
      },
    }
  }

  // The model the current mode sends to
  const activeModel = computed(() => ({ image: selected.image, video: selected.video })[mode.value] ?? selected.text)

  return {
    selected,
    mode,
    memoryIndex,
    imageIndex,
    historyLimit,
    imageLimit,
    imageOpts,
    videoOpts,
    textInfo,
    imageInfo,
    videoInfo,
    imageRatioOptions,
    imageResOptions,
    videoRatioOptions,
    videoResOptions,
    durationOptions,
    showImageOpts,
    showVideoOpts,
    currentMode,
    activeModel,
    cycleMode,
    applyDefaults,
    applyChat,
    turnSettings,
  }
}

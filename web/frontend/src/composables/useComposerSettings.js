import { ref, reactive, computed, watch, nextTick } from 'vue'

// The chat composer's settings: models, mode, the memory and image sliders
// and the media options. Remembered per browser (the last ones used) and per
// chat (restored when it's opened).

export const MODES = [
  { id: 'auto', label: 'Auto', icon: '✦' },
  { id: 'text', label: 'Chat', icon: '💬' },
  { id: 'image', label: 'Image', icon: '🖼' },
  { id: 'video', label: 'Video', icon: '🎬' },
  { id: 'audio', label: 'Audio', icon: '🔊' },
]
const DEFAULT_RATIOS = ['1:1', '16:9', '9:16', '4:3', '3:4', '3:2', '2:3', '21:9']
// First id containing one of these wins when nothing is remembered yet
const PREFERRED = {
  text: ['anthropic/claude-sonnet', 'google/gemini', 'openai/gpt'],
  image: ['gemini', 'seedream', 'flux', 'gpt-image'],
  video: ['veo', 'seedance', 'wan', 'sora'],
  audio: ['eleven', 'suno', 'minimax'],
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

// "auto"/"adaptive" are dropped from the list: the "Ratio: auto" placeholder
// already stands for them (the backend sends the model's own auto value when
// the ratio is left unset), so showing them again is a confusing duplicate.
const AUTO_RATIOS = ['auto', 'adaptive']
const ratiosOf = info => {
  const ratios = info?.aspect_ratios?.length ? info.aspect_ratios : DEFAULT_RATIOS
  return ratios.filter(r => !AUTO_RATIOS.includes(r))
}

// A newly picked model may not offer the old picks — fall back to auto/default
function dropUnsupported(opts, ratios, resolutions, durations = null) {
  if (opts.aspect_ratio && !ratios.includes(opts.aspect_ratio)) opts.aspect_ratio = ''
  if (opts.resolution && !resolutions.includes(opts.resolution)) opts.resolution = ''
  if (durations && opts.duration && !durations.includes(Number(opts.duration))) opts.duration = ''
}

// Audio option -> [the model option that offers it, how to clean the raw value]
const num = v => (v === null || v === '' ? null : Number(v))
const text = v => (v || '').trim() || null
const AUDIO_FIELDS = {
  voice: ['voice', v => v || null],
  speed: ['tuning', num],
  volume: ['tuning', num],
  pitch: ['tuning', num],
  instrumental: ['instrumental', v => !!v],
  vocal_gender: ['instrumental', (v, o) => (o.instrumental ? null : v || null)],
  style: ['lyrics', text],
  title: ['lyrics', text],
  negative_prompt: ['instrumental', text],
  duration: ['duration', num],
}

/** `models`: the catalogues ({ text, image, video, audio } lists) the pickers choose from. */
export function useComposerSettings(models) {
  const prefs = loadPrefs()
  const selected = reactive({
    text: prefs.text || '',
    image: prefs.image ?? '',
    video: prefs.video ?? '',
    audio: prefs.audio ?? '',
  })
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
  // Length of the attached source clip, snapped to what the model allows (set by useStudio)
  const clipDuration = ref(null)
  // Speech / music settings; '' / null = the model's own default
  const audioOpts = reactive({
    voice: '',
    speed: null,
    volume: null,
    pitch: null,
    instrumental: false,
    vocal_gender: '',
    style: '',
    title: '',
    negative_prompt: '',
    duration: '',
    ...prefs.audioOpts,
  })
  // Reference images switched on (sent first) or off (never sent) in the
  // composer: chat filenames or "char:<id>/<file>". Per chat, not per browser.
  const refChoices = reactive({ on: [], off: [] })

  watch(
    [
      () => ({ ...selected }),
      mode,
      memoryIndex,
      imageIndex,
      () => ({ ...imageOpts }),
      () => ({ ...videoOpts }),
      () => ({ ...audioOpts }),
    ],
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
            audioOpts: { ...audioOpts },
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
  const audioInfo = computed(() => models.audio.find(m => m.id === selected.audio))
  const imageRatioOptions = computed(() => ratiosOf(imageInfo.value))
  const imageResOptions = computed(() => imageInfo.value?.resolutions || [])
  const videoRatioOptions = computed(() => ratiosOf(videoInfo.value))
  const videoResOptions = computed(() => videoInfo.value?.resolutions || [])
  const durationOptions = computed(() => videoInfo.value?.durations || [])
  // Source-file tools (upscale, face swap…) carry no ratio / duration of their own
  const imageShowsRatio = computed(() => !imageInfo.value?.tool)
  const videoShowsRatio = computed(() => !(videoInfo.value?.type && !videoInfo.value.aspect_ratios))
  const videoShowsDuration = computed(() => !(videoInfo.value?.type && !videoInfo.value.durations))
  const showImageOpts = computed(() => !!selected.image && ['auto', 'image'].includes(mode.value))
  const showVideoOpts = computed(() => !!selected.video && ['auto', 'video'].includes(mode.value))
  const showAudioOpts = computed(() => !!selected.audio && mode.value === 'audio')
  const currentMode = computed(() => MODES.find(m => m.id === mode.value) || MODES[0])

  watch(imageInfo, info => {
    if (info) dropUnsupported(imageOpts, imageRatioOptions.value, imageResOptions.value)
  })
  watch(videoInfo, (info, prev) => {
    if (!info) return
    dropUnsupported(videoOpts, videoRatioOptions.value, videoResOptions.value, durationOptions.value)
    // Audio starts on for every model that offers it, so a choice made on one
    // model never silently carries over (e.g. an "off" left from another). Only
    // when the model really changes — not when the catalogue first loads on a
    // page refresh, which would undo the remembered choice (and a loaded preset).
    if (info.generate_audio && prev && prev.id !== info.id) videoOpts.generate_audio = true
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
    if (!('audio' in prefs)) selected.audio = pickDefault('audio')
  }

  // A chat's own models and settings, restored when it's opened
  function applyChat(conv) {
    for (const kind of ['text', 'image', 'video']) {
      if (conv[`${kind}_model`]) selected[kind] = conv[`${kind}_model`]
    }
    const st = conv.settings
    if (st?.audio_model) selected.audio = st.audio_model
    setRefChoices(st?.ref_choices)
    if (!st) return
    if (MODES.some(m => m.id === st.mode)) mode.value = st.mode
    setStep(memoryIndex, MEMORY_STEPS, st.history_limit)
    setStep(imageIndex, IMAGE_STEPS, st.image_limit)
    Object.assign(imageOpts, optionsOrUnset(st.image_options, ['aspect_ratio', 'resolution']))
    Object.assign(videoOpts, optionsOrUnset(st.video_options, ['aspect_ratio', 'resolution', 'duration']))
    if (st.video_options?.generate_audio != null) videoOpts.generate_audio = st.video_options.generate_audio
    if (st.audio_options) Object.assign(audioOpts, st.audio_options)
  }

  // Presets: a named snapshot of the models + media options + mode, loaded in
  // one click. Per browser (localStorage), like the rest of the composer prefs.
  const PRESETS_KEY = 'studio.presets'
  const presets = ref(readPresets())
  function readPresets() {
    try {
      const list = JSON.parse(localStorage.getItem(PRESETS_KEY))
      return Array.isArray(list) ? list : []
    } catch {
      return []
    }
  }
  function storePresets() {
    try {
      localStorage.setItem(PRESETS_KEY, JSON.stringify(presets.value))
    } catch {
      /* storage unavailable */
    }
  }
  const snapshot = () => ({
    mode: mode.value,
    models: { ...selected },
    imageOpts: { ...imageOpts },
    videoOpts: { ...videoOpts },
    audioOpts: { ...audioOpts },
  })
  // The saved preset the setup currently matches (so the picker can show it),
  // or '' once anything has been changed away from it
  const keyed = s =>
    JSON.stringify([s.mode, s.models, s.imageOpts, s.videoOpts, s.audioOpts], (k, v) =>
      v && typeof v === 'object' && !Array.isArray(v)
        ? Object.fromEntries(Object.entries(v).sort(([a], [b]) => (a < b ? -1 : 1)))
        : v,
    )
  const activePresetId = computed(() => {
    const now = keyed(snapshot())
    return presets.value.find(p => keyed(p) === now)?.id || ''
  })
  function savePreset(name, snap = snapshot()) {
    const preset = { id: Date.now().toString(36), name, ...snap }
    // Same name replaces, so re-saving updates a preset
    presets.value = [...presets.value.filter(p => p.name !== name), preset]
    storePresets()
  }
  // Change a preset: its name and/or its settings (a snapshot)
  function updatePreset(id, patch) {
    presets.value = presets.value.map(p => (p.id === id ? { ...p, ...patch } : p))
    storePresets()
  }
  function deletePreset(id) {
    presets.value = presets.value.filter(p => p.id !== id)
    storePresets()
  }
  async function loadPreset(preset) {
    Object.assign(selected, preset.models)
    if (MODES.some(m => m.id === preset.mode)) mode.value = preset.mode
    // Let the model-change watchers (drop unsupported options, reset audio) run
    // first, then put the preset's own options back on top.
    await nextTick()
    Object.assign(imageOpts, preset.imageOpts)
    Object.assign(videoOpts, preset.videoOpts)
    Object.assign(audioOpts, preset.audioOpts)
  }

  function setRefChoices(choices) {
    refChoices.on = [...(choices?.on || [])]
    refChoices.off = [...(choices?.off || [])]
  }

  // Only what the picked model takes goes out (the rest stays the model's default)
  function audioSettings() {
    const has = opt => audioInfo.value?.options?.includes(opt)
    const out = {}
    for (const [field, [option, clean]] of Object.entries(AUDIO_FIELDS)) {
      out[field] = has(option) ? clean(audioOpts[field], audioOpts) : null
    }
    return out
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
      audio_model: selected.audio || null,
      image_options: { aspect_ratio: imageOpts.aspect_ratio || null, resolution: imageOpts.resolution || null },
      video_options: {
        aspect_ratio: videoOpts.aspect_ratio || null,
        resolution: videoOpts.resolution || null,
        // '' = Auto: the attached clip's length (reference-to-video), else the model's default
        duration: videoOpts.duration ? Number(videoOpts.duration) : clipDuration.value,
        generate_audio: videoInfo.value?.generate_audio ? videoOpts.generate_audio : null,
      },
      audio_options: audioSettings(),
      ref_choices: { on: [...refChoices.on], off: [...refChoices.off] },
    }
  }

  // The picked model's catalogue entry for the current mode (null in Chat / Auto)
  const activeInfo = computed(
    () => ({ image: imageInfo, video: videoInfo, audio: audioInfo })[mode.value]?.value ?? null,
  )

  return {
    selected,
    mode,
    memoryIndex,
    imageIndex,
    historyLimit,
    imageLimit,
    imageOpts,
    videoOpts,
    audioOpts,
    refChoices,
    setRefChoices,
    textInfo,
    imageInfo,
    videoInfo,
    audioInfo,
    imageRatioOptions,
    imageResOptions,
    videoRatioOptions,
    videoResOptions,
    durationOptions,
    imageShowsRatio,
    videoShowsRatio,
    videoShowsDuration,
    activeInfo,
    showImageOpts,
    showVideoOpts,
    showAudioOpts,
    currentMode,
    cycleMode,
    presets,
    snapshot,
    savePreset,
    activePresetId,
    updatePreset,
    deletePreset,
    loadPreset,
    applyDefaults,
    applyChat,
    turnSettings,
    clipDuration,
  }
}

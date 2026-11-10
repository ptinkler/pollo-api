// Capability tags (mirrors web/providers/model_tags.py TAGS, same order): the
// labels, and one colour per tag. The model picker's row badges and its filter
// menu both read these, so a tag looks the same everywhere.

export const TAG_LABELS = {
  img2vid: 'Image→Video',
  text2vid: 'Text→Video',
  ref2vid: 'References→Video',
  video_refs: 'Video refs (recast)',
  first_last: 'First+Last frame',
  video_edit: 'Video edit',
  video_extend: 'Video extend',
  motion: 'Motion / recast',
  lipsync: 'Lip sync',
  upscale: 'Upscale',
  audio: 'Makes audio',
  bg_remove: 'Background remove',
  subtitle_remove: 'Subtitle remove',
  face_swap: 'Face swap',
  tts: 'Text→Speech',
  music: 'Music',
  text2img: 'Text→Image',
  image_edit: 'Image edit',
  tools: 'Image tools',
  vision: 'Vision',
  functions: 'Tools / functions',
}

// Hues step by the golden angle, so every tag lands well away from the ones
// before it; lightness alternates to pull neighbours further apart.
const GOLDEN_ANGLE = 137.508
const SLUGS = Object.keys(TAG_LABELS)

export function tagColor(slug) {
  const i = Math.max(0, SLUGS.indexOf(slug))
  return `hsl(${Math.round((i * GOLDEN_ANGLE) % 360)} 72% ${i % 2 ? 72 : 62}%)`
}

// One pastel per provider, defined once in style.css (--p-*) so the picker
// tags, the filter chips and the usage cards all agree.
export const PROVIDER_COLOR = {
  pollo: 'var(--p-pollo)',
  venice: 'var(--p-venice)',
  openrouter: 'var(--p-openrouter)',
}

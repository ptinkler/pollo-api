import { shortModel } from './format'

const cap = s => s[0].toUpperCase() + s.slice(1)

const kindOf = p => (['image', 'video', 'audio'].includes(p.mode) ? p.mode : 'video')
const optsOf = (p, kind) => ({ image: p.imageOpts, video: p.videoOpts, audio: {} })[kind] || {}

// One line for a card: "Video · seedance25v1 · 16:9 · 720p"
export function presetSummary(p) {
  const kind = kindOf(p)
  const opts = optsOf(p, kind)
  return [cap(kind), shortModel(p.models?.[kind]) || 'no model', opts.aspect_ratio, opts.resolution]
    .filter(Boolean)
    .join(' · ')
}

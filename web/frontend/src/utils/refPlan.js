// Which reference images the next image will be sent with, and which won't
// fit the image model (mirrors _plan_refs in web/chat.py). The priority:
// `lead` (attachments), the ones switched on, each character's main image,
// the other chat images (pins), then the characters' other images.

export const charRef = (id, file) => `char:${id}/${file}`

const dedupe = list => [...new Set(list)]

// Each character's images, up to `perCharacter` each, taken round-robin
function characterRefs(characters, off, perCharacter = Infinity) {
  const files = characters.map(c => (c.images || []).map(f => charRef(c.id, f)).filter(r => !off.has(r)))
  const out = []
  const rounds = Math.min(perCharacter, Math.max(0, ...files.map(f => f.length)))
  for (let i = 0; i < rounds; i++) for (const f of files) if (i < f.length) out.push(f[i])
  return out
}

/**
 * `lead`, `chat`: chat image refs (filenames), `characters`: { id, images },
 * `imageLimit`: cap on chat images (null = all), `maxRefs`: the model's
 * maximum (null = unknown), `choices`: { on, off } from the composer.
 * Returns { sent, dropped, off } lists of refs, `sent` in send order.
 */
export function planRefs({ lead = [], chat = [], characters = [], imageLimit = null, maxRefs = null, choices = {} }) {
  const on = choices.on || []
  const off = new Set(choices.off || [])
  const offChat = dedupe([...lead, ...chat]).filter(r => off.has(r))
  const kept = dedupe([...lead, ...chat]).filter(r => !off.has(r))
  const chatRefs = imageLimit == null ? kept : kept.slice(0, imageLimit)
  const split = Math.min(dedupe(lead).filter(r => !off.has(r)).length, chatRefs.length)
  const every = characterRefs(characters, off)
  const mains = characterRefs(characters, off, 1)
  const candidates = new Set([...kept, ...every]) // a switched-on chat image goes even over the slider
  const ordered = dedupe([
    ...chatRefs.slice(0, split),
    ...on.filter(r => candidates.has(r)),
    ...mains,
    ...chatRefs.slice(split),
    ...every,
  ])
  const offChars = characters.flatMap(c => (c.images || []).map(f => charRef(c.id, f))).filter(r => off.has(r))
  const n = maxRefs == null ? ordered.length : maxRefs
  return { sent: ordered.slice(0, n), dropped: ordered.slice(n), off: [...offChat, ...offChars] }
}

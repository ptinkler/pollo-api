// Turning the Generate form's references into what /api/generate takes, and
// checking them against a model's limits before anything is uploaded or billed

export const REF_TYPE_LABELS = {
  image: 'Image',
  subject: 'Subject',
  video: 'Video',
  audio: 'Audio',
  file: 'Document',
  link: 'Web page',
}

const label = type => REF_TYPE_LABELS[type] || type
const trimmed = url => (url || '').trim()

/** v1 models (Ref mode): just { type, url } — no names, order or subjects. */
export function v1Refs(refs) {
  return refs.filter(r => trimmed(r.url)).map(r => ({ type: r.type, url: trimmed(r.url) }))
}

/**
 * Why v1 refs can't be sent to a model ("ref_mode" in its info), or null.
 * `characterRefs`: attached characters bring images of their own.
 */
export function v1RefsError(refs, info, { characterRefs = false, length = null } = {}) {
  const counts = {}
  for (const r of refs) counts[r.type] = (counts[r.type] || 0) + 1
  const overLimit = Object.entries(info.limits || {}).find(([type, limit]) => (counts[type] || 0) > limit)
  const badType = refs.find(r => !info.types.includes(r.type))
  const checks = [
    [
      !characterRefs && !refs.some(r => r.type !== 'audio'),
      () => 'At least one non-audio reference (or a character with images) is required',
    ],
    [badType, () => `This model doesn't accept ${label(badType.type)} references`],
    [refs.length > info.max, () => `Too many references (max ${info.max})`],
    [overLimit, () => `Too many ${label(overLimit[0])} references (max ${overLimit[1]})`],
    [
      (info.exclusive || []).filter(t => counts[t]).length > 1,
      () => `Can't combine ${info.exclusive.map(label).join(' and ')} references`,
    ],
    [
      info.max_length_with_video && counts.video && length > info.max_length_with_video,
      () => `Length must be ${info.max_length_with_video}s or less with a video reference`,
    ],
  ]
  const failed = checks.find(([fails]) => fails)
  return failed ? failed[1]() : null
}

/**
 * Legacy "ref" models: named refs, the URL under the type's key, numbered in
 * order (subjects aren't numbered). Empty rows are left out.
 */
export function legacyRefs(refs) {
  let order = 1
  const out = []
  for (const r of refs) {
    const name = (r.name || `ref${out.length + 1}`).slice(0, 20)
    if (r.type === 'subject') {
      const images = (r.images || []).filter(img => trimmed(img.url)).map(img => ({ url: trimmed(img.url) }))
      if (images.length) out.push({ type: 'subject', name, images, subjectId: r.subjectId || '' })
      continue
    }
    const url = trimmed(r.url)
    if (!url) continue
    const type = ['video', 'audio'].includes(r.type) ? r.type : 'image'
    out.push({ type, name, [type]: url, order: order++ })
  }
  return out
}

const isLocal = url => !!url && url.startsWith('local:')

/** Whether the request has local images the server must upload first (a slower start). */
export function hasLocalUploads(data) {
  const localRef = r =>
    (r.type === 'image' && isLocal(r.image || r.url)) ||
    (r.type === 'subject' && (r.images || []).some(img => isLocal(img.url)))
  return isLocal(data.image_url) || (data.refs || []).some(localRef)
}

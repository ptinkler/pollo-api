import { describe, it, expect } from 'vitest'
import { hasLocalUploads, legacyRefs, v1Refs, v1RefsError } from '../utils/generateRefs'
import { takeFiles } from '../utils/files'

const INFO = { types: ['image', 'video', 'audio'], max: 3, limits: { video: 1 }, exclusive: ['video', 'audio'] }

describe('v1 refs', () => {
  it('keeps filled-in rows as { type, url }', () => {
    expect(
      v1Refs([
        { type: 'image', url: ' a ', name: 'x' },
        { type: 'video', url: '  ' },
      ]),
    ).toEqual([{ type: 'image', url: 'a' }])
  })

  it('checks them against the model', () => {
    const img = { type: 'image', url: 'a' }
    expect(v1RefsError([img], INFO)).toBeNull()
    expect(v1RefsError([{ type: 'audio', url: 'a' }], INFO)).toMatch(/non-audio/)
    expect(v1RefsError([{ type: 'audio', url: 'a' }], INFO, { characterRefs: true })).toBeNull()
    expect(v1RefsError([{ type: 'link', url: 'a' }], INFO)).toBe("This model doesn't accept Web page references")
    expect(v1RefsError([img, img, img, img], INFO)).toBe('Too many references (max 3)')
    const video = { type: 'video', url: 'v' }
    expect(v1RefsError([img, video, video], INFO)).toBe('Too many Video references (max 1)')
    expect(v1RefsError([video, { type: 'audio', url: 'a' }], INFO)).toBe("Can't combine Video and Audio references")
    const capped = { ...INFO, max_length_with_video: 10 }
    expect(v1RefsError([video], capped, { length: 15 })).toMatch(/10s or less/)
    expect(v1RefsError([video], capped, { length: 10 })).toBeNull()
  })
})

describe('legacy refs', () => {
  it('names and numbers them, the URL under the type, subjects unnumbered', () => {
    const refs = legacyRefs([
      { type: 'image', url: 'i' },
      { type: 'video', url: '' },
      { type: 'subject', images: [{ url: ' s ' }, { url: '' }], subjectId: 'sub' },
      { type: 'audio', name: 'a very long name indeed, over twenty', url: 'au' },
    ])
    expect(refs).toEqual([
      { type: 'image', name: 'ref1', image: 'i', order: 1 },
      { type: 'subject', name: 'ref2', images: [{ url: 's' }], subjectId: 'sub' },
      { type: 'audio', name: 'a very long name ind', audio: 'au', order: 2 },
    ])
  })
})

describe('hasLocalUploads', () => {
  it('spots local source and ref images', () => {
    expect(hasLocalUploads({ image_url: 'https://x' })).toBe(false)
    expect(hasLocalUploads({ image_url: 'local:a.png' })).toBe(true)
    expect(hasLocalUploads({ refs: [{ type: 'image', image: 'local:a.png' }] })).toBe(true)
    expect(hasLocalUploads({ refs: [{ type: 'subject', images: [{ url: 'local:b.png' }] }] })).toBe(true)
    expect(hasLocalUploads({ refs: [{ type: 'video', video: 'local:c.mp4' }] })).toBe(false)
  })
})

describe('takeFiles', () => {
  it('copies the picked files and clears the input', () => {
    const files = [{ name: 'a.png' }]
    const target = { files, value: 'C:\\fakepath\\a.png' }
    expect(takeFiles({ target })).toEqual(files)
    expect(target.value).toBe('')
  })
})

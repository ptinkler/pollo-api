import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { ref } from 'vue'
import MediaLightbox from '../components/chat/MediaLightbox.vue'
import { useChatAttachments, MAX_ATTACHMENTS } from '../composables/useChatAttachments'

describe('MediaLightbox', () => {
  it('offers uses for a chat image and closes on Escape', async () => {
    const w = mount(MediaLightbox, { props: { item: { url: '/x.png', file: 'x.png' } }, attachTo: document.body })
    document.querySelector('.lightbox-animate').click()
    expect(w.emitted('use-image')).toEqual([[{ file: 'x.png', mode: 'image' }]])
    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))
    expect(w.emitted('close')).toHaveLength(1)
    w.unmount()
  })
})

describe('useChatAttachments', () => {
  it('takes chat images up to the limit, once each', () => {
    const showToast = vi.fn()
    const a = useChatAttachments({ convId: ref('c1'), ensureConversation: async () => 'c1', showToast })
    expect(a.addChatImage('one.png')).toBe(true)
    expect(a.addChatImage('one.png')).toBe(true)
    expect(a.attachments.value).toHaveLength(1)
    for (let i = 1; i < MAX_ATTACHMENTS; i++) a.addChatImage(`${i}.png`)
    expect(a.addChatImage('extra.png')).toBe(false)
    expect(showToast).toHaveBeenCalledWith(`Up to ${MAX_ATTACHMENTS} attachments per message`, 'error')
    expect(a.files.value).toHaveLength(MAX_ATTACHMENTS)
  })

  it('uploads pasted, dropped or picked images to this chat', async () => {
    const calls = []
    globalThis.fetch = vi.fn(async (url, opts) => {
      calls.push([String(url), opts?.method])
      return { ok: true, status: 200, json: async () => ({ file: 'up_1.png' }) }
    })
    URL.createObjectURL = vi.fn(() => 'blob:x')
    const a = useChatAttachments({ convId: ref('c1'), ensureConversation: async () => 'c1', showToast: vi.fn() })
    a.addFiles([new File(['x'], 'a.png', { type: 'image/png' })])
    await vi.waitFor(() => expect(a.files.value).toEqual(['up_1.png']))
    expect(calls).toEqual([['/api/chat/conversations/c1/attachments', 'POST']])
  })
})

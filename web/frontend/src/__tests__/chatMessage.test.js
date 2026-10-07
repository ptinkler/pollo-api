import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import ChatMessage from '../components/chat/ChatMessage.vue'

const image = { id: 'm1', kind: 'image', source: 'generated', status: 'done', file: 'img_a.png', prompt: 'a fox' }
const video = { id: 'm2', kind: 'video', source: 'generated', status: 'done', file: 'vid_a.mp4' }

describe('ChatMessage "make a video from this image"', () => {
  it('is offered on generated images, not videos', async () => {
    const w = mount(ChatMessage, { props: { convId: 'c1', message: {
      id: 1, role: 'assistant', content: '', status: 'done', media: [image, video] } } })
    const buttons = w.findAll('button[title="Make a video from this image"]')
    expect(buttons).toHaveLength(1)
    await buttons[0].trigger('click')
    expect(w.emitted('use-image')).toEqual([[{ file: 'img_a.png', mode: 'video' }]])
  })

  it('is offered on the user\'s own attachments', async () => {
    const w = mount(ChatMessage, { props: { convId: 'c1', message: {
      id: 2, role: 'user', content: 'look', status: 'done',
      media: [{ id: 'u1', kind: 'image', source: 'upload', status: 'done', file: 'up_b.png' }] } } })
    await w.find('button[title="Make a video from this image"]').trigger('click')
    expect(w.emitted('use-image')).toEqual([[{ file: 'up_b.png', mode: 'video' }]])
  })

  it('passes the file to the image viewer so it can offer it too', async () => {
    const w = mount(ChatMessage, { props: { convId: 'c1', message: {
      id: 3, role: 'assistant', content: '', status: 'done', media: [image] } } })
    await w.find('.media-item img').trigger('click')
    expect(w.emitted('open-media')[0][0]).toMatchObject({ kind: 'image', file: 'img_a.png' })
  })
})

describe('ChatMessage media settings', () => {
  it('shows the settings a video was made with, while rendering and when done', async () => {
    const params = { duration: 5, resolution: '480p', aspect_ratio: null, first_frame: 'img_a.png', generate_audio: true }
    const pending = { id: 'v1', kind: 'video', source: 'generated', status: 'pending', prompt: 'waves', params }
    const w = mount(ChatMessage, { props: { convId: 'c1', message: {
      id: 4, role: 'assistant', content: '', status: 'done', created_at: new Date().toISOString(), media: [pending] } } })
    expect(w.find('.pending-specs').text()).toBe('from image · 5s · 480p · audio')
    await w.setProps({ message: { id: 4, role: 'assistant', content: '', status: 'done',
      media: [{ ...pending, status: 'done', file: 'vid.mp4' }] } })
    expect(w.find('.caption-specs').text()).toBe('from image · 5s · 480p · audio')
  })

  it('shows ratio and resolution for images', () => {
    const w = mount(ChatMessage, { props: { convId: 'c1', message: { id: 5, role: 'assistant', content: '', status: 'done',
      media: [{ ...image, model: 'pollo/seedreamv1', params: { aspect_ratio: '16:9', resolution: '2K', refs: [] } }] } } })
    expect(w.find('.caption-specs').text()).toBe('2K · 16:9')
  })
})

describe('ChatMessage mode tag', () => {
  const user = (mode) => mount(ChatMessage, { props: { convId: 'c1', canEdit: true,
    message: { id: 6, role: 'user', content: 'waves', status: 'done', mode } } })

  it('marks prompts sent outside Auto mode', () => {
    expect(user('video').find('.mode-tag').text()).toBe('🎬 Video')
    expect(user('image').find('.mode-tag').text()).toBe('🖼 Image')
  })

  it('stays quiet for Auto and older messages', () => {
    expect(user('auto').find('.mode-tag').exists()).toBe(false)
    expect(user(null).find('.mode-tag').exists()).toBe(false)
  })
})

describe('ChatMessage "make a picture" and text-to-media', () => {
  it('offers a picture-from-image button beside the video one', async () => {
    const w = mount(ChatMessage, { props: { convId: 'c1', message: {
      id: 7, role: 'assistant', content: '', status: 'done', media: [image] } } })
    await w.find('button[title="Make a picture from this image"]').trigger('click')
    expect(w.emitted('use-image')).toEqual([[{ file: 'img_a.png', mode: 'image' }]])
  })

  it('turns a text reply into a picture or video prompt', async () => {
    const w = mount(ChatMessage, { props: { convId: 'c1', message: {
      id: 8, role: 'assistant', content: 'A lighthouse on a cliff at dusk.', status: 'done', media: [] } } })
    await w.find('button[title^="Make a picture from this reply"]').trigger('click')
    await w.find('button[title^="Make a video from this reply"]').trigger('click')
    expect(w.emitted('use-text')).toEqual([
      [{ text: 'A lighthouse on a cliff at dusk.', mode: 'image' }],
      [{ text: 'A lighthouse on a cliff at dusk.', mode: 'video' }],
    ])
  })

  it('uses just the selected part of the reply', async () => {
    const w = mount(ChatMessage, { attachTo: document.body, props: { convId: 'c1', message: {
      id: 9, role: 'assistant', content: 'First idea.\n\nSecond idea: a red kite.', status: 'done', media: [] } } })
    const para = w.findAll('.markdown p')[1].element
    const range = document.createRange()
    range.selectNodeContents(para)
    window.getSelection().removeAllRanges()
    window.getSelection().addRange(range)
    await w.find('button[title^="Make a picture from this reply"]').trigger('click')
    expect(w.emitted('use-text')[0][0]).toEqual({ text: 'Second idea: a red kite.', mode: 'image' })
    window.getSelection().removeAllRanges()
    w.unmount()
  })

  it('has no text-to-media buttons on media-only replies', () => {
    const w = mount(ChatMessage, { props: { convId: 'c1', message: {
      id: 10, role: 'assistant', content: '', status: 'done', media: [image] } } })
    expect(w.find('button[title^="Make a picture from this reply"]').exists()).toBe(false)
  })
})

describe('ChatMessage pin as reference', () => {
  it('is offered on generated images and uploads, not videos, and toggles', async () => {
    const w = mount(ChatMessage, { props: { convId: 'c1', message: {
      id: 5, role: 'assistant', content: '', status: 'done', media: [image, video] } } })
    const pins = w.findAll('.pin-btn')
    expect(pins).toHaveLength(1)
    await pins[0].trigger('click')
    expect(w.emitted('pin')).toEqual([[{ mediaId: 'm1', pinned: true }]])
    await w.setProps({ message: { id: 5, role: 'assistant', content: '', status: 'done',
      media: [{ ...image, pinned: true }, video] } })
    expect(w.find('.pin-btn').classes()).toContain('on')
    await w.find('.pin-btn').trigger('click')
    expect(w.emitted('pin')[1]).toEqual([{ mediaId: 'm1', pinned: false }])

    const u = mount(ChatMessage, { props: { convId: 'c1', message: {
      id: 6, role: 'user', content: 'this is Linh', status: 'done',
      media: [{ id: 'u1', kind: 'image', source: 'upload', status: 'done', file: 'up_b.png' }] } } })
    expect(u.findAll('.pin-btn')).toHaveLength(1)
  })

  it('is not offered before the message is saved', () => {
    const w = mount(ChatMessage, { props: { convId: 'c1', message: {
      id: 'tmp-1', role: 'user', content: 'x', status: 'done',
      media: [{ id: 'u1', kind: 'image', source: 'upload', status: 'done', file: 'up_b.png' }] } } })
    expect(w.find('.pin-btn').exists()).toBe(false)
  })
})

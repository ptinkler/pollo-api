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
    expect(w.emitted('animate')).toEqual([['img_a.png']])
  })

  it('is offered on the user\'s own attachments', async () => {
    const w = mount(ChatMessage, { props: { convId: 'c1', message: {
      id: 2, role: 'user', content: 'look', status: 'done',
      media: [{ id: 'u1', kind: 'image', source: 'upload', status: 'done', file: 'up_b.png' }] } } })
    await w.find('button[title="Make a video from this image"]').trigger('click')
    expect(w.emitted('animate')).toEqual([['up_b.png']])
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

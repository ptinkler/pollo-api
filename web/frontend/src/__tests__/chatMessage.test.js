import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import ChatMessage from '../components/chat/ChatMessage.vue'

const image = { id: 'm1', kind: 'image', source: 'generated', status: 'done', file: 'img_a.png', prompt: 'a fox' }
const video = { id: 'm2', kind: 'video', source: 'generated', status: 'done', file: 'vid_a.mp4' }

describe('ChatMessage "make a video from this image"', () => {
  it('is offered on generated images, not videos', async () => {
    const w = mount(ChatMessage, {
      props: {
        convId: 'c1',
        message: {
          id: 1,
          role: 'assistant',
          content: '',
          status: 'done',
          media: [image, video],
        },
      },
    })
    const buttons = w.findAll('button[title="Attach this picture and switch to Video mode"]')
    expect(buttons).toHaveLength(1)
    await buttons[0].trigger('click')
    expect(w.emitted('use-image')).toEqual([[{ file: 'img_a.png', mode: 'video' }]])
  })

  it("is offered on the user's own attachments", async () => {
    const w = mount(ChatMessage, {
      props: {
        convId: 'c1',
        message: {
          id: 2,
          role: 'user',
          content: 'look',
          status: 'done',
          media: [{ id: 'u1', kind: 'image', source: 'upload', status: 'done', file: 'up_b.png' }],
        },
      },
    })
    await w.find('button[title="Attach this picture and switch to Video mode"]').trigger('click')
    expect(w.emitted('use-image')).toEqual([[{ file: 'up_b.png', mode: 'video' }]])
  })

  it('passes the file to the image viewer so it can offer it too', async () => {
    const w = mount(ChatMessage, {
      props: {
        convId: 'c1',
        message: {
          id: 3,
          role: 'assistant',
          content: '',
          status: 'done',
          media: [image],
        },
      },
    })
    await w.find('.media-item img').trigger('click')
    expect(w.emitted('open-media')[0][0]).toMatchObject({ kind: 'image', file: 'img_a.png' })
  })
})

describe('ChatMessage media settings', () => {
  it('shows the settings a video was made with, while rendering and when done', async () => {
    const params = {
      duration: 5,
      resolution: '480p',
      aspect_ratio: null,
      first_frame: 'img_a.png',
      generate_audio: true,
    }
    const pending = { id: 'v1', kind: 'video', source: 'generated', status: 'pending', prompt: 'waves', params }
    const w = mount(ChatMessage, {
      props: {
        convId: 'c1',
        message: {
          id: 4,
          role: 'assistant',
          content: '',
          status: 'done',
          created_at: new Date().toISOString(),
          media: [pending],
        },
      },
    })
    expect(w.find('.pending-specs').text()).toBe('from image · 5s · 480p · audio')
    await w.setProps({
      message: {
        id: 4,
        role: 'assistant',
        content: '',
        status: 'done',
        media: [{ ...pending, status: 'done', file: 'vid.mp4' }],
      },
    })
    expect(w.find('.caption-specs').text()).toBe('from image · 5s · 480p · audio')
  })

  it('shows ratio and resolution for images', () => {
    const w = mount(ChatMessage, {
      props: {
        convId: 'c1',
        message: {
          id: 5,
          role: 'assistant',
          content: '',
          status: 'done',
          media: [{ ...image, model: 'pollo/seedream', params: { aspect_ratio: '16:9', resolution: '2K', refs: [] } }],
        },
      },
    })
    expect(w.find('.caption-specs').text()).toBe('2K · 16:9')
  })
})

describe('ChatMessage mode tag', () => {
  const user = mode =>
    mount(ChatMessage, {
      props: { convId: 'c1', canEdit: true, message: { id: 6, role: 'user', content: 'waves', status: 'done', mode } },
    })

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
    const w = mount(ChatMessage, {
      props: {
        convId: 'c1',
        message: {
          id: 7,
          role: 'assistant',
          content: '',
          status: 'done',
          media: [image],
        },
      },
    })
    await w.find('button[title="Attach this picture and switch to Image mode"]').trigger('click')
    expect(w.emitted('use-image')).toEqual([[{ file: 'img_a.png', mode: 'image' }]])
  })

  it('no longer offers the reply-text-to-prompt buttons', () => {
    const w = mount(ChatMessage, {
      props: {
        convId: 'c1',
        message: { id: 9, role: 'assistant', content: 'Some words.', status: 'done', media: [] },
      },
    })
    expect(w.find('button[title$="as an Image-mode prompt"]').exists()).toBe(false)
    expect(w.find('button[title$="as a Video-mode prompt"]').exists()).toBe(false)
  })
})

describe('ChatMessage pin as reference', () => {
  it('is offered on generated images and uploads, not videos, and toggles', async () => {
    const w = mount(ChatMessage, {
      props: {
        convId: 'c1',
        message: {
          id: 5,
          role: 'assistant',
          content: '',
          status: 'done',
          media: [image, video],
        },
      },
    })
    const pins = w.findAll('.pin-btn')
    expect(pins).toHaveLength(1)
    await pins[0].trigger('click')
    expect(w.emitted('pin')).toEqual([[{ mediaId: 'm1', pinned: true }]])
    await w.setProps({
      message: { id: 5, role: 'assistant', content: '', status: 'done', media: [{ ...image, pinned: true }, video] },
    })
    expect(w.find('.pin-btn').classes()).toContain('on')
    await w.find('.pin-btn').trigger('click')
    expect(w.emitted('pin')[1]).toEqual([{ mediaId: 'm1', pinned: false }])

    const u = mount(ChatMessage, {
      props: {
        convId: 'c1',
        message: {
          id: 6,
          role: 'user',
          content: 'this is Linh',
          status: 'done',
          media: [{ id: 'u1', kind: 'image', source: 'upload', status: 'done', file: 'up_b.png' }],
        },
      },
    })
    expect(u.findAll('.pin-btn')).toHaveLength(1)
  })

  it('is not offered before the message is saved', () => {
    const w = mount(ChatMessage, {
      props: {
        convId: 'c1',
        message: {
          id: 'tmp-1',
          role: 'user',
          content: 'x',
          status: 'done',
          media: [{ id: 'u1', kind: 'image', source: 'upload', status: 'done', file: 'up_b.png' }],
        },
      },
    })
    expect(w.find('.pin-btn').exists()).toBe(false)
  })
})

describe('ChatMessage delete', () => {
  it('is offered on saved prompts, not replies', async () => {
    const user = mount(ChatMessage, {
      props: {
        convId: 'c1',
        canEdit: true,
        message: {
          id: 7,
          role: 'user',
          content: 'draw a cat',
          status: 'done',
          media: [],
        },
      },
    })
    await user.find('button[title^="Delete this prompt"]').trigger('click')
    expect(user.emitted('delete')).toHaveLength(1)
    const reply = mount(ChatMessage, {
      props: {
        convId: 'c1',
        canEdit: false,
        message: {
          id: 8,
          role: 'assistant',
          content: 'Meow',
          status: 'done',
          media: [],
        },
      },
    })
    expect(reply.find('button[title^="Delete this prompt"]').exists()).toBe(false)
  })
})

describe('ChatMessage branch to a new chat', () => {
  it('is offered on saved prompts, not replies', async () => {
    const user = mount(ChatMessage, {
      props: {
        convId: 'c1',
        canEdit: true,
        message: {
          id: 7,
          role: 'user',
          content: 'draw a cat',
          status: 'done',
          media: [],
        },
      },
    })
    await user.find('button[title^="Start a new chat from here"]').trigger('click')
    expect(user.emitted('fork')).toHaveLength(1)
    const reply = mount(ChatMessage, {
      props: {
        convId: 'c1',
        message: {
          id: 8,
          role: 'assistant',
          content: 'Meow',
          status: 'done',
          media: [],
        },
      },
    })
    expect(reply.find('button[title^="Start a new chat from here"]').exists()).toBe(false)
  })
})

describe('ChatMessage branches', () => {
  it('offers Branch on replies too', async () => {
    const w = mount(ChatMessage, {
      props: {
        convId: 'c1',
        canBranch: true,
        message: {
          id: 9,
          role: 'assistant',
          content: 'Meow',
          status: 'done',
          media: [],
        },
      },
    })
    await w.find('button[title^="Start a new chat from here: everything up to this reply"]').trigger('click')
    expect(w.emitted('fork')).toHaveLength(1)
  })

  it('lists the chats branched off a message and opens one', async () => {
    const forks = [
      { id: 'b1', title: 'Fox (branch)' },
      { id: 'b2', title: 'Other' },
    ]
    const w = mount(ChatMessage, {
      props: {
        convId: 'c1',
        message: {
          id: 7,
          role: 'user',
          content: 'draw a fox',
          status: 'done',
          media: [],
          forks,
        },
      },
    })
    expect(w.find('.fork-toggle').text()).toBe('⑂ 2 branches')
    await w.find('.fork-toggle').trigger('click')
    const items = w.findAll('.fork-item')
    expect(items.map(i => i.text())).toEqual(['Fox (branch)', 'Other'])
    await items[1].trigger('click')
    expect(w.emitted('open-chat')).toEqual([['b2']])
    expect(w.find('.fork-menu').exists()).toBe(false)
  })
})

describe('ChatMessage refs sent', () => {
  it('says when a model took fewer reference images than were picked', () => {
    const item = { ...image, params: { refs: ['a.png', 'b.png', 'c.png'], refs_used: 1 } }
    const w = mount(ChatMessage, {
      props: {
        convId: 'c1',
        message: {
          id: 9,
          role: 'assistant',
          content: '',
          status: 'done',
          media: [item],
        },
      },
    })
    expect(w.find('.media-caption').text()).toContain('🔗 1 of 3 refs')
    const all = mount(ChatMessage, {
      props: {
        convId: 'c1',
        message: {
          id: 10,
          role: 'assistant',
          content: '',
          status: 'done',
          media: [{ ...image, params: { refs: ['a.png', 'b.png'] } }],
        },
      },
    })
    expect(all.find('.media-caption').text()).toContain('🔗 2 refs')
  })

  it('shows thumbnails of the refs on hover, dimming the ones not sent', async () => {
    const item = { ...image, params: { refs: ['a.png', 'char:7/b.png'], refs_used: 1 } }
    const w = mount(ChatMessage, {
      attachTo: document.body,
      props: { convId: 'c1', message: { id: 11, role: 'assistant', content: '', status: 'done', media: [item] } },
    })
    await w.find('.caption-refs').trigger('mouseenter')
    const imgs = document.querySelectorAll('.refs-peek img')
    expect([...imgs].map(i => i.getAttribute('src'))).toEqual([
      '/api/chat/media/c1/a.png',
      '/api/characters/7/images/b.png',
    ])
    expect([...imgs].map(i => i.classList.contains('unused'))).toEqual([false, true])
    await w.find('.caption-refs').trigger('mouseleave')
    expect(document.querySelector('.refs-peek')).toBeNull()
    w.unmount()
  })
})

describe('ChatMessage request view', () => {
  it('shows what a card sent to the provider', async () => {
    const request = { model: 'seedream-v5-pro-edit', prompt: 'a fox', images: ['data:image/png;base64,… (90 KB)'] }
    const w = mount(ChatMessage, {
      attachTo: document.body,
      global: { stubs: { RouterLink: { template: '<a><slot /></a>' } } },
      props: {
        convId: 'c1',
        message: {
          id: 3,
          role: 'assistant',
          content: '',
          status: 'done',
          media: [
            {
              id: 'm',
              kind: 'image',
              source: 'generated',
              status: 'error',
              error: 'Venice: blocked',
              prompt: 'a fox',
              model: 'venice/seedream-v5-pro',
              request,
              response: { error: 'Your prompt violates the content policy' },
            },
          ],
        },
      },
    })
    await w.find('button[title="Show exactly what was sent to the provider"]').trigger('click')
    const dialog = document.querySelector('.req-dialog')
    expect(dialog.textContent).toContain('"model": "seedream-v5-pro-edit"')
    expect(dialog.textContent).toContain('Venice: blocked')
    expect(dialog.textContent).toContain('"error": "Your prompt violates the content policy"')
    w.unmount()
  })

  it('has no request button for media without one', () => {
    const w = mount(ChatMessage, {
      props: {
        convId: 'c1',
        message: {
          id: 4,
          role: 'assistant',
          content: '',
          status: 'done',
          media: [
            { id: 'n', kind: 'image', source: 'generated', status: 'done', file: 'x.png', prompt: 'p', model: 'a/b' },
          ],
        },
      },
    })
    expect(w.find('button[title="Show exactly what was sent to the provider"]').exists()).toBe(false)
  })
})

const reply = (media, extra = {}) => ({
  props: {
    convId: 'c1',
    message: { id: 42, role: 'assistant', content: 'Here you go.', status: 'done', media, ...extra },
  },
})

describe('ChatMessage edit and redo a picture in place', () => {
  it('offers Edit only on a picture, Redo on anything it can make again', () => {
    const img = mount(ChatMessage, reply([image]))
    expect(img.find('button[title^="Edit this picture"]').exists()).toBe(true)
    expect(img.find('button[title^="Make it again"]').exists()).toBe(true)
    const vid = mount(ChatMessage, reply([{ ...video, prompt: 'waves' }]))
    expect(vid.find('button[title^="Edit this picture"]').exists()).toBe(false)
    expect(vid.find('button[title^="Make it again"]').exists()).toBe(true)
  })

  it('Edit opens an empty box and asks to edit this picture', async () => {
    const w = mount(ChatMessage, reply([image]))
    await w.find('button[title^="Edit this picture"]').trigger('click')
    const box = w.find('.prompt-box textarea')
    expect(box.element.value).toBe('')
    expect(box.attributes('placeholder')).toBe('Describe the change…')
    await box.setValue('give it a hat')
    await w.find('.prompt-box .edit-send').trigger('click')
    expect(w.emitted('regenerate')[0][0]).toEqual({
      mediaId: 'm1',
      model: null,
      prompt: 'give it a hat',
      edit: true,
      replace: true,
    })
  })

  it('Redo pre-fills the prompt it was made with and does not edit', async () => {
    const w = mount(ChatMessage, reply([image]))
    await w.find('button[title^="Make it again"]').trigger('click')
    expect(w.find('.prompt-box textarea').element.value).toBe('a fox')
    await w.find('.prompt-box .edit-send').trigger('click')
    expect(w.emitted('regenerate')[0][0]).toMatchObject({ prompt: 'a fox', edit: false, replace: true })
  })

  it('will not send an empty prompt', async () => {
    const w = mount(ChatMessage, reply([image]))
    await w.find('button[title^="Edit this picture"]').trigger('click')
    expect(w.find('.prompt-box .edit-send').attributes('disabled')).toBeDefined()
    await w.find('.prompt-box .edit-send').trigger('click')
    expect(w.emitted('regenerate')).toBeUndefined()
  })

  it('Cancel closes the box without regenerating', async () => {
    const w = mount(ChatMessage, reply([image]))
    await w.find('button[title^="Make it again"]').trigger('click')
    await w.find('.prompt-box .meta-btn').trigger('click')
    expect(w.find('.prompt-box').exists()).toBe(false)
    expect(w.emitted('regenerate')).toBeUndefined()
  })

  it('neither is offered while the reply is still streaming', () => {
    const w = mount(ChatMessage, reply([image], { status: 'streaming' }))
    expect(w.find('button[title^="Edit this picture"]').exists()).toBe(false)
    expect(w.find('button[title^="Make it again"]').exists()).toBe(false)
  })
})

describe('ChatMessage earlier versions of a picture', () => {
  const versioned = {
    ...image,
    file: 'img_new.png',
    prompt: 'a fox in a hat',
    versions: [{ file: 'img_a.png', prompt: 'a fox' }],
  }

  it('shows no arrows until a picture has been replaced', () => {
    expect(
      mount(ChatMessage, reply([image]))
        .find('.ver-nav')
        .exists(),
    ).toBe(false)
  })

  it('counts the live picture as the last version', () => {
    const w = mount(ChatMessage, reply([versioned]))
    expect(w.find('.ver-nav span').text()).toBe('2/2')
  })

  it('flips back to the picture it replaced', async () => {
    const w = mount(ChatMessage, reply([versioned]))
    const [back, forward] = w.findAll('.ver-nav button')
    expect(forward.attributes('disabled')).toBeDefined() // already on the newest
    await back.trigger('click')
    expect(w.find('.ver-nav span').text()).toBe('1/2')
    expect(w.find('img').attributes('src')).toContain('img_a.png')
    await w.findAll('.ver-nav button')[0].trigger('click') // can't go past the oldest
    expect(w.find('.ver-nav span').text()).toBe('1/2')
  })
})

describe('ChatMessage reword a reply', () => {
  // Rewording is offered where Retry is: on the newest reply of a branch
  const latest = media => {
    const r = reply(media)
    return { props: { ...r.props, canRetry: true } }
  }

  it('is offered on a reply that made media, and emits reword', async () => {
    const w = mount(ChatMessage, latest([image]))
    await w.find('button[title^="Write these words again"]').trigger('click')
    expect(w.emitted('reword')).toHaveLength(1)
  })

  it('is not offered on a reply with no media to keep', () => {
    expect(mount(ChatMessage, latest([])).find('button[title^="Write these words again"]').exists()).toBe(false)
  })

  it('is not offered on an older reply, where Retry is not either', () => {
    const w = mount(ChatMessage, reply([image]))
    expect(w.find('button[title^="Write these words again"]').exists()).toBe(false)
  })
})

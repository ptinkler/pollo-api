/**
 * Tests for composables/useProjectSettings.js
 */
import { describe, it, expect, beforeEach } from 'vitest'
import { ref, nextTick } from 'vue'
import { useProjectSettings } from '../composables/useProjectSettings.js'

beforeEach(() => {
  localStorage.clear()
})

describe('useProjectSettings', () => {
  it('returns default settings', () => {
    const projectName = ref('test')
    const { settings } = useProjectSettings(projectName)
    expect(settings.value.model).toBe('pollodance20')
    expect(settings.value.aspect_ratio).toBe('9:16')
    expect(settings.value.resolution).toBe('480p')
    expect(settings.value.length).toBe(10)
    expect(settings.value.generate_audio).toBe(false)
    expect(settings.value.web_search).toBe(false)
  })

  it('saves and loads settings', () => {
    const projectName = ref('savetest')
    const { settings, save } = useProjectSettings(projectName)
    settings.value.model = 'pollodance20'
    settings.value.length = 20
    save()

    // Create a new instance, should load saved settings
    const { settings: loaded } = useProjectSettings(ref('savetest'))
    expect(loaded.value.model).toBe('pollodance20')
    expect(loaded.value.length).toBe(20)
  })

  it('separate projects have separate settings', () => {
    const proj1 = ref('proj1')
    const { settings: s1, save: save1 } = useProjectSettings(proj1)
    s1.value.model = 'pollodance20'
    save1()

    const proj2 = ref('proj2')
    const { settings: s2, save: save2 } = useProjectSettings(proj2)
    s2.value.model = 'pollodance20'
    save2()

    const { settings: loaded1 } = useProjectSettings(ref('proj1'))
    const { settings: loaded2 } = useProjectSettings(ref('proj2'))
    expect(loaded1.value.model).toBe('pollodance20')
    expect(loaded2.value.model).toBe('pollodance20')
  })

  it('applyProjectData applies URLs if not set', () => {
    const projectName = ref('apply')
    const { settings, applyProjectData } = useProjectSettings(projectName)
    applyProjectData({
      image_url: 'https://img.com/i.jpg',
    })
    expect(settings.value.image_url).toBe('https://img.com/i.jpg')
  })

  it('applyProjectData does not overwrite existing URLs', () => {
    const projectName = ref('nooverwrite')
    const { settings, applyProjectData } = useProjectSettings(projectName)
    settings.value.image_url = 'https://existing.com/img.jpg'
    applyProjectData({
      image_url: 'https://new.com/img.jpg',
    })
    expect(settings.value.image_url).toBe('https://existing.com/img.jpg')
  })

  it('applyJobSettings applies all settings from job', () => {
    const projectName = ref('jobapply')
    const { settings, applyJobSettings } = useProjectSettings(projectName)
    applyJobSettings({
      model: 'pollodance20',
      aspect_ratio: '16:9',
      resolution: '720p',
      length: 15,
      generate_audio: true,
      params: {
        web_search: true,
        image_tail: 'https://tail.jpg',
      },
      image_url: 'https://img.com/i.jpg',
    })
    expect(settings.value.model).toBe('pollodance20')
    expect(settings.value.aspect_ratio).toBe('16:9')
    expect(settings.value.resolution).toBe('720p')
    expect(settings.value.length).toBe(15)
    expect(settings.value.generate_audio).toBe(true)
    expect(settings.value.web_search).toBe(true)
    expect(settings.value.image_tail).toBe('https://tail.jpg')
    expect(settings.value.image_url).toBe('https://img.com/i.jpg')
  })

  it('applyJobSettings handles missing params', () => {
    const projectName = ref('jobmissing')
    const { settings, applyJobSettings } = useProjectSettings(projectName)
    applyJobSettings({
      model: 'pollodance20',
    })
    expect(settings.value.model).toBe('pollodance20')
    expect(settings.value.web_search).toBe(false)
    expect(settings.value.image_tail).toBe('')
  })

  it('loads on project name change', async () => {
    // Save settings for 'first' with one model
    const projectName = ref('first')
    const { settings, save } = useProjectSettings(projectName)
    settings.value.model = 'pollo20'
    save()

    // Pre-save settings for 'second' with a different model
    localStorage.setItem('pollo_settings_second', JSON.stringify({ model: 'pollodance20' }))

    // Switch project — should load 'second' settings
    projectName.value = 'second'
    await nextTick()
    expect(settings.value.model).toBe('pollodance20')
  })

  it('handles corrupt localStorage gracefully', () => {
    localStorage.setItem('pollo_settings_corrupt', 'not-json')
    const projectName = ref('corrupt')
    const { settings } = useProjectSettings(projectName)
    // Should fall back to defaults
    expect(settings.value.model).toBe('pollodance20')
  })
})


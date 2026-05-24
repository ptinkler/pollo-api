import { ref, watch, inject } from 'vue'
import { fetchProject, deleteVideo } from './useApi'

/**
 * Shared composable for video list panels (Gallery, Archive).
 *
 * @param {Object} props - Component props (must include `project` and `active`)
 * @param {Object} options
 * @param {boolean} options.archived - Whether to fetch archived or non-archived videos
 * @param {Function} options.emit - Component emit function
 */
export function useVideoList(props, { archived, emit }) {
  const showToast = inject('showToast')
  const videos = ref([])
  const loading = ref(false)

  async function load() {
    loading.value = true
    try {
      const data = await fetchProject(props.project, { archived })
      videos.value = data.videos || []
    } catch (err) {
      const label = archived ? 'archived videos' : 'videos'
      showToast(`Failed to load ${label}`, 'error')
      videos.value = []
    } finally {
      loading.value = false
    }
  }

  async function handleDelete(video) {
    if (!confirm('Delete this video permanently?')) return
    try {
      await deleteVideo(props.project, video.filename)
      videos.value = videos.value.filter(v => v.filename !== video.filename)
      emit('video-deleted', video.filename)
      showToast('Video deleted', 'success')
    } catch (err) {
      showToast('Failed to delete video', 'error')
    }
  }

  function openVideo(video) {
    emit('open-video', video)
  }

  function handleRegenerate(video) {
    emit('regenerate', video)
  }

  function getVideoByFilename(filename) {
    return videos.value.find(v => v.filename === filename)
  }

  function removeVideo(filename) {
    videos.value = videos.value.filter(v => v.filename !== filename)
  }

  // Load when active or when project changes
  watch([() => props.active, () => props.project], ([active]) => {
    if (active) load()
  }, { immediate: true })

  return {
    videos,
    loading,
    load,
    handleDelete,
    openVideo,
    handleRegenerate,
    getVideoByFilename,
    removeVideo,
    showToast,
  }
}


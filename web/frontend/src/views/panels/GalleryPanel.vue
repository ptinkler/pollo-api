<script setup>
import VideoCard from '../../components/VideoCard.vue'
import { archiveJob } from '../../composables/useApi'
import { useVideoList } from '../../composables/useVideoList'

const props = defineProps({
  project: { type: String, required: true },
  active: { type: Boolean, default: false }
})

const emit = defineEmits(['open-video', 'regenerate', 'use-as-ref', 'video-deleted'])

const {
  videos, loading, load,
  handleDelete, openVideo, handleRegenerate,
  getVideoByFilename, removeVideo, showToast,
} = useVideoList(props, { archived: false, emit })

async function handleArchive(video) {
  if (!video.job?.job_id) {
    showToast('Cannot archive: no job ID', 'error')
    return
  }
  try {
    await archiveJob(video.job.job_id)
    videos.value = videos.value.filter(v => v.filename !== video.filename)
    showToast('Video archived', 'success')
  } catch (err) {
    showToast('Failed to archive', 'error')
  }
}

function addVideo(video) {
  // Deduplicate: skip if already in list
  if (videos.value.some(v => v.filename === video.filename)) return
  // Add to beginning of list (newest first)
  videos.value = [video, ...videos.value]
}

function refresh() {
  load()
}

// Expose methods for parent
defineExpose({ refresh, getVideoByFilename, removeVideo, addVideo })
</script>

<template>
  <div class="gallery-panel">
    <div v-if="loading" class="loading">
      <p>Loading...</p>
    </div>

    <div v-else-if="!videos.length" class="empty-state">
      <h3>No videos yet</h3>
      <p>Generate one first</p>
    </div>

    <div v-else class="gallery-grid">
      <VideoCard
        v-for="video in videos"
        :key="video.filename"
        :video="video"
        :project="project"
        :show-archive="true"
        :show-unarchive="false"
        @click="openVideo"
        @regenerate="handleRegenerate"
        @use-as-ref="(v) => emit('use-as-ref', v)"
        @archive="handleArchive"
        @delete="handleDelete"
      />
    </div>
  </div>
</template>

<style scoped>
/* .gallery-grid, .loading, .empty-state are in global style.css */
</style>

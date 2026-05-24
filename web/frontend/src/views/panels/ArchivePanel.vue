<script setup>
import VideoCard from '../../components/VideoCard.vue'
import { unarchiveJob } from '../../composables/useApi'
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
} = useVideoList(props, { archived: true, emit })

async function handleUnarchive(video) {
  if (!video.job?.job_id) {
    showToast('Cannot unarchive: no job ID', 'error')
    return
  }
  try {
    await unarchiveJob(video.job.job_id)
    videos.value = videos.value.filter(v => v.filename !== video.filename)
    showToast('Video unarchived', 'success')
  } catch (err) {
    showToast('Failed to unarchive', 'error')
  }
}

function refresh() {
  load()
}

// Expose methods for parent
defineExpose({ refresh, getVideoByFilename, removeVideo })
</script>

<template>
  <div class="archive-panel">
    <div v-if="loading" class="loading">
      <p>Loading...</p>
    </div>

    <div v-else-if="!videos.length" class="empty-state">
      <h3>No archived videos</h3>
      <p>Videos you archive will appear here</p>
    </div>

    <div v-else class="gallery-grid">
      <VideoCard
        v-for="video in videos"
        :key="video.filename"
        :video="video"
        :project="project"
        :show-archive="false"
        :show-unarchive="true"
        @click="openVideo"
        @regenerate="handleRegenerate"
        @use-as-ref="(v) => emit('use-as-ref', v)"
        @unarchive="handleUnarchive"
        @delete="handleDelete"
      />
    </div>
  </div>
</template>

<style scoped>
/* .gallery-grid, .loading, .empty-state are in global style.css */
</style>


<script setup>
import { ref, computed } from 'vue'
import VideoCard from '../../components/VideoCard.vue'
import MoveToProjectModal from '../../components/MoveToProjectModal.vue'
import { useVideoList } from '../../composables/useVideoList'

const props = defineProps({
  project: { type: String, required: true },
  active: { type: Boolean, default: false }
})

const emit = defineEmits(['open-video', 'regenerate', 'use-as-ref', 'video-deleted'])

const {
  videos, loading, load,
  handleDelete, openVideo, handleRegenerate, handleToggleFavourite, handleArchive,
  getVideoByFilename, removeVideo,
  selectMode, selectedFilenames, toggleSelectMode, toggleSelect,
  showMoveModal, pendingMoveJobIds, handleCardMove, handleBulkMove, handleMove, handleBulkDelete,
} = useVideoList(props, { archived: false, emit })

// Filter state
const showVideos = ref(true)
const showImages = ref(true)
const favouritesOnly = ref(false)
const filteredVideos = computed(() => videos.value.filter(v => {
  if (favouritesOnly.value && !v.favourite) return false
  const mt = v.media_type || v.job?.media_type || v.job?.job_type || 'video'
  if (mt === 'image') return showImages.value
  return showVideos.value
}))

function addVideo(video) {
  if (videos.value.some(v => v.filename === video.filename)) return
  videos.value = [video, ...videos.value]
}

function refresh() { load() }

defineExpose({ refresh, getVideoByFilename, removeVideo, addVideo })
</script>

<template>
  <div class="gallery-panel">
    <div v-if="loading" class="loading">
      <p>Loading...</p>
    </div>

    <template v-else-if="videos.length">
      <div class="panel-toolbar">
        <div class="filter-checks">
          <label class="filter-check">
            <input type="checkbox" v-model="showVideos" /> Videos
          </label>
          <label class="filter-check">
            <input type="checkbox" v-model="showImages" /> Images
          </label>
          <label class="filter-check">
            <input type="checkbox" v-model="favouritesOnly" /> ★ Favourites only
          </label>
        </div>
        <button class="btn btn-secondary toolbar-btn" @click="toggleSelectMode">
          {{ selectMode ? 'Cancel' : 'Select' }}
        </button>
      </div>

      <div v-if="selectMode && selectedFilenames.size > 0" class="selection-bar">
        <span>{{ selectedFilenames.size }} selected</span>
        <div class="selection-actions">
          <button class="btn btn-primary" @click="handleBulkMove">Move to project</button>
          <button class="btn btn-danger" @click="handleBulkDelete">Delete</button>
        </div>
      </div>

      <div v-if="!filteredVideos.length" class="empty-state">
        <h3>Nothing matches these filters</h3>
        <p v-if="favouritesOnly">Star (☆) a video or image to see it here.</p>
      </div>

      <div v-else class="gallery-grid">
        <VideoCard
          v-for="video in filteredVideos"
          :key="video.filename"
          :video="video"
          :project="project"
          :show-archive="!selectMode"
          :show-unarchive="false"
          :show-move="!selectMode"
          :selectable="selectMode"
          :selected="selectedFilenames.has(video.filename)"
          @click="openVideo"
          @regenerate="handleRegenerate"
          @use-as-ref="(v) => emit('use-as-ref', v)"
          @archive="handleArchive"
          @move="handleCardMove"
          @delete="handleDelete"
          @toggle-favourite="handleToggleFavourite"
          @toggle-select="toggleSelect"
        />
      </div>
    </template>

    <div v-else class="empty-state">
      <h3>Nothing here yet</h3>
      <p>Generate something first</p>
    </div>

    <MoveToProjectModal
      :visible="showMoveModal"
      :current-project="project"
      :count="pendingMoveJobIds.length"
      @move="handleMove"
      @close="showMoveModal = false"
    />
  </div>
</template>

<style scoped>
.panel-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}

.filter-checks {
  display: flex;
  gap: 12px;
}

.filter-check {
  display: flex;
  align-items: center;
  gap: 5px;
  font-size: 0.85rem;
  color: var(--text2);
  cursor: pointer;
  user-select: none;
}

.filter-check input {
  accent-color: var(--accent);
  cursor: pointer;
}

.toolbar-btn {
  font-size: 0.8rem;
  padding: 5px 12px;
}

.selection-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: var(--surface);
  border: 1px solid var(--accent);
  border-radius: 8px;
  padding: 8px 14px;
  margin-bottom: 12px;
  font-size: 0.9rem;
  color: var(--text2);
}

.selection-actions {
  display: flex;
  gap: 8px;
}
</style>

<script setup>
import VideoCard from '../../components/VideoCard.vue'
import MoveToProjectModal from '../../components/MoveToProjectModal.vue'
import { useVideoList } from '../../composables/useVideoList'

const props = defineProps({
  project: { type: String, required: true },
  active: { type: Boolean, default: false },
})

const emit = defineEmits(['open-video', 'regenerate', 'use-as-ref', 'video-deleted'])

const {
  videos,
  loading,
  load,
  handleDelete,
  openVideo,
  handleRegenerate,
  handleToggleFavourite,
  handleUnarchive,
  getVideoByFilename,
  removeVideo,
  selectMode,
  selectedFilenames,
  toggleSelectMode,
  toggleSelect,
  showMoveModal,
  pendingMoveJobIds,
  handleCardMove,
  handleBulkMove,
  handleMove,
  handleBulkDelete,
} = useVideoList(props, { archived: true, emit })

function refresh() {
  load()
}

defineExpose({ refresh, getVideoByFilename, removeVideo })
</script>

<template>
  <div class="archive-panel">
    <div v-if="loading" class="loading">
      <p>Loading...</p>
    </div>

    <template v-else-if="videos.length">
      <div class="panel-toolbar">
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

      <div class="gallery-grid">
        <VideoCard
          v-for="video in videos"
          :key="video.filename"
          :video="video"
          :project="project"
          :show-archive="false"
          :show-unarchive="!selectMode"
          :show-move="!selectMode"
          :selectable="selectMode"
          :selected="selectedFilenames.has(video.filename)"
          @click="openVideo"
          @regenerate="handleRegenerate"
          @use-as-ref="v => emit('use-as-ref', v)"
          @unarchive="handleUnarchive"
          @move="handleCardMove"
          @delete="handleDelete"
          @toggle-favourite="handleToggleFavourite"
          @toggle-select="toggleSelect"
        />
      </div>
    </template>

    <div v-else class="empty-state">
      <h3>No archived videos</h3>
      <p>Videos you archive will appear here</p>
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
  justify-content: flex-end;
  margin-bottom: 12px;
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

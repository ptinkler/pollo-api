<script setup>
import { ref, computed, onMounted, inject } from 'vue'
import { useRouter } from 'vue-router'
import ProjectCard from '../components/ProjectCard.vue'
import VideoCard from '../components/VideoCard.vue'
import {
  fetchProjects,
  createProject,
  archiveProject,
  unarchiveProject,
  deleteProject,
  fetchFavourites,
} from '../composables/useApi'
import { toggleFavourite } from '../composables/useVideoList'

const router = useRouter()
const showToast = inject('showToast')

const projects = ref([])
const newProjectName = ref('')
const loading = ref(true)
const activeTab = ref('active') // 'active' | 'archived' | 'favourites'

// ── Favourites: starred generations from every project ──
const favourites = ref([])
const favFilter = ref('all') // all | video | image
const shownFavourites = computed(() =>
  favFilter.value === 'all' ? favourites.value : favourites.value.filter(f => f.media_type === favFilter.value),
)

async function loadFavourites() {
  loading.value = true
  try {
    favourites.value = (await fetchFavourites()).items
  } catch {
    showToast('Failed to load favourites', 'error')
  } finally {
    loading.value = false
  }
}

function openFavourite(item) {
  // Archived generations aren't in the gallery, so open the project's Archive tab
  if (item.job?.archived) return router.push({ name: 'project-archive', params: { project: item.project } })
  router.push({ name: 'project-video', params: { project: item.project, videoFilename: item.filename } })
}

async function unstar(item) {
  await toggleFavourite(item, showToast)
  if (!item.favourite) favourites.value = favourites.value.filter(f => f !== item)
}

async function loadProjects() {
  if (activeTab.value === 'favourites') return loadFavourites()
  loading.value = true
  try {
    const archived = activeTab.value === 'archived'
    projects.value = await fetchProjects({ archived })
  } catch (err) {
    showToast('Failed to load projects', 'error')
  } finally {
    loading.value = false
  }
}

function switchTab(tab) {
  if (activeTab.value === tab) return
  activeTab.value = tab
  loadProjects()
}

function openProject(project) {
  router.push({ name: 'project-gallery', params: { project: project.slug } })
}

async function handleCreate() {
  const name = newProjectName.value.trim()
  if (!name) return

  try {
    const result = await createProject({ name })
    newProjectName.value = ''
    // Route using the slug returned by the API
    router.push({ name: 'project-generate', params: { project: result.slug } })
  } catch (err) {
    showToast('Failed to create project', 'error')
  }
}

async function handleToggleArchive(project, archive) {
  const action = archive ? 'archive' : 'unarchive'
  try {
    await (archive ? archiveProject : unarchiveProject)(project.slug)
    projects.value = projects.value.filter(p => p.slug !== project.slug)
    showToast(`Project ${action}d`, 'success')
  } catch (err) {
    showToast(`Failed to ${action} project`, 'error')
  }
}

async function handleDelete(project) {
  if (!confirm(`Delete project "${project.name}" and all its videos? This cannot be undone.`)) return
  try {
    await deleteProject(project.slug)
    projects.value = projects.value.filter(p => p.slug !== project.slug)
    showToast('Project deleted', 'success')
  } catch (err) {
    showToast('Failed to delete project', 'error')
  }
}

function handleKeydown(e) {
  if (e.key === 'Enter') {
    e.preventDefault()
    handleCreate()
  }
}

onMounted(loadProjects)
</script>

<template>
  <div class="home-view">
    <div class="home-bar">
      <input v-model="newProjectName" type="text" placeholder="New project name..." @keydown="handleKeydown" />
      <button class="btn btn-primary" @click="handleCreate">+ Create</button>
    </div>

    <div class="tab-bar">
      <button class="tab-btn" :class="{ active: activeTab === 'active' }" @click="switchTab('active')">Projects</button>
      <button class="tab-btn" :class="{ active: activeTab === 'archived' }" @click="switchTab('archived')">
        Archived
      </button>
      <button class="tab-btn" :class="{ active: activeTab === 'favourites' }" @click="switchTab('favourites')">
        ★ Favourites
      </button>
    </div>

    <template v-if="activeTab === 'favourites'">
      <div v-if="favourites.length" class="fav-filters">
        <button
          v-for="f in [
            ['all', 'All'],
            ['video', 'Videos'],
            ['image', 'Images'],
          ]"
          :key="f[0]"
          :class="['fav-filter', { active: favFilter === f[0] }]"
          @click="favFilter = f[0]"
        >
          {{ f[1] }}
        </button>
      </div>
      <div v-if="loading" class="loading"><p>Loading...</p></div>
      <div v-else-if="!shownFavourites.length" class="empty-state">
        <h3>{{ favourites.length ? 'Nothing here with this filter' : 'No favourites yet' }}</h3>
        <p>Star (☆) any video or image in a project's gallery to keep it here.</p>
      </div>
      <div v-else class="fav-grid">
        <VideoCard
          v-for="item in shownFavourites"
          :key="item.filename"
          :video="item"
          :project="item.project"
          :project-name="item.project_name"
          :manage="false"
          @click="openFavourite"
          @toggle-favourite="unstar"
        />
      </div>
    </template>

    <div v-else-if="loading" class="loading">
      <p>Loading...</p>
    </div>

    <div v-else-if="!projects.length" class="empty-state">
      <template v-if="activeTab === 'active'">
        <h3>No projects yet</h3>
        <p>Create one above to get started</p>
      </template>
      <template v-else>
        <h3>No archived projects</h3>
        <p>Projects you archive will appear here</p>
      </template>
    </div>

    <div v-else class="projects-grid">
      <ProjectCard
        v-for="project in projects"
        :key="project.slug"
        :project="project"
        :show-archive="activeTab === 'active'"
        :show-unarchive="activeTab === 'archived'"
        @click="openProject"
        @archive="p => handleToggleArchive(p, true)"
        @unarchive="p => handleToggleArchive(p, false)"
        @delete="handleDelete"
      />
    </div>
  </div>
</template>

<style scoped>
.fav-filters {
  display: flex;
  gap: 6px;
  margin-bottom: 14px;
}

.fav-filter {
  background: var(--surface2);
  border: 1px solid var(--border);
  color: var(--text2);
  border-radius: 999px;
  padding: 4px 12px;
  font-size: 0.8rem;
  cursor: pointer;
}

.fav-filter.active {
  color: var(--text);
  border-color: var(--accent);
}

.fav-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
  gap: 16px;
}

.home-bar {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 16px;
}

.home-bar input {
  flex: 1;
  background: var(--surface2);
  border: 1px solid var(--border);
  color: var(--text);
  padding: 10px 14px;
  border-radius: 8px;
  font-size: 0.95rem;
  outline: none;
}

.home-bar input:focus {
  border-color: var(--accent);
}

.tab-bar {
  display: flex;
  gap: 4px;
  margin-bottom: 20px;
  border-bottom: 1px solid var(--border);
  padding-bottom: 0;
}

.tab-btn {
  background: none;
  border: none;
  border-bottom: 2px solid transparent;
  color: var(--text2);
  padding: 8px 16px;
  font-size: 0.9rem;
  cursor: pointer;
  transition:
    color 0.15s,
    border-color 0.15s;
}

.tab-btn:hover {
  color: var(--text);
}

.tab-btn.active {
  color: var(--accent);
  border-bottom-color: var(--accent);
}

.projects-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
  gap: 16px;
}
</style>

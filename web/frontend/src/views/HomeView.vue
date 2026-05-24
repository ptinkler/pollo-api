<script setup>
import { ref, onMounted, inject } from 'vue'
import { useRouter } from 'vue-router'
import ProjectCard from '../components/ProjectCard.vue'
import { fetchProjects, createProject, archiveProject, unarchiveProject, deleteProject } from '../composables/useApi'

const router = useRouter()
const showToast = inject('showToast')

const projects = ref([])
const newProjectName = ref('')
const loading = ref(true)
const activeTab = ref('active')  // 'active' or 'archived'

async function loadProjects() {
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
      <input
        v-model="newProjectName"
        type="text"
        placeholder="New project name..."
        @keydown="handleKeydown"
      />
      <button class="btn btn-primary" @click="handleCreate">+ Create</button>
    </div>

    <div class="tab-bar">
      <button
        class="tab-btn"
        :class="{ active: activeTab === 'active' }"
        @click="switchTab('active')"
      >Projects</button>
      <button
        class="tab-btn"
        :class="{ active: activeTab === 'archived' }"
        @click="switchTab('archived')"
      >Archived</button>
    </div>

    <div v-if="loading" class="loading">
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
  transition: color 0.15s, border-color 0.15s;
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

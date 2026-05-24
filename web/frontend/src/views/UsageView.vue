<script setup>
import { ref, onMounted, computed } from 'vue'
import { fetchUsage, fetchBalance, fetchUsageProjectDetails, getVideoThumbUrl, getFilenameFromPath } from '../composables/useApi'

const usage = ref(null)
const balance = ref(null)
const loading = ref(true)
const days = ref(30)
const expandedProjects = ref({})
const projectJobs = ref({})
const projectLoading = ref({})

async function loadUsage() {
  loading.value = true
  try {
    const [usageData, balanceData] = await Promise.all([
      fetchUsage(days.value),
      fetchBalance().catch(() => null),
    ])
    usage.value = usageData
    balance.value = balanceData
    // Reset expansions on reload
    expandedProjects.value = {}
    projectJobs.value = {}
  } catch (err) {
    console.error('Failed to load usage:', err)
  } finally {
    loading.value = false
  }
}

async function toggleProject(projectSlug) {
  if (expandedProjects.value[projectSlug]) {
    expandedProjects.value[projectSlug] = false
    return
  }
  expandedProjects.value[projectSlug] = true
  if (!projectJobs.value[projectSlug]) {
    projectLoading.value[projectSlug] = true
    try {
      projectJobs.value[projectSlug] = await fetchUsageProjectDetails(projectSlug, days.value)
    } catch (err) {
      projectJobs.value[projectSlug] = []
    } finally {
      projectLoading.value[projectSlug] = false
    }
  }
}

function changePeriod(newDays) {
  days.value = newDays
  loadUsage()
}

const maxModelCredits = computed(() => {
  if (!usage.value?.by_model) return 0
  return Math.max(...Object.values(usage.value.by_model).map(m => m.credits))
})

const maxDayCredits = computed(() => {
  if (!usage.value?.by_day?.length) return 0
  return Math.max(...usage.value.by_day.map(([, c]) => c))
})

function barPercent(credits, maxCredits) {
  return maxCredits > 0 ? `${(credits / maxCredits) * 100}%` : '0%'
}

function barWidth(credits) {
  return barPercent(credits, maxModelCredits.value)
}

function dayBarWidth(credits) {
  return barPercent(credits, maxDayCredits.value)
}

function formatDate(dateStr) {
  const d = new Date(dateStr + 'T00:00:00')
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
}

function formatDateTime(isoStr) {
  if (!isoStr) return ''
  return new Date(isoStr).toLocaleString('en-US', { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' })
}

function getThumbUrl(projectSlug, job) {
  if (!job.video_exists || !job.video_path) return null
  const filename = getFilenameFromPath(job.video_path)
  return getVideoThumbUrl(projectSlug, filename)
}

onMounted(loadUsage)
</script>

<template>
  <div class="usage-view">
    <header class="usage-header">
      <h1>Credit Usage</h1>
      <div class="period-selector">
        <button
          v-for="d in [7, 30, 90]"
          :key="d"
          :class="{ active: days === d }"
          @click="changePeriod(d)"
        >{{ d }}d</button>
      </div>
    </header>

    <div v-if="loading" class="loading"><p>Loading...</p></div>

    <template v-else-if="usage">
      <!-- Balance Card -->
      <div v-if="balance" class="balance-card">
        <div class="balance-available">
          <span class="balance-value">{{ balance.availableCredits.toLocaleString() }}</span>
          <span class="balance-label">credits available</span>
        </div>
        <div class="balance-total">
          of {{ balance.totalCredits.toLocaleString() }} total
        </div>
      </div>

      <!-- Summary Cards -->
      <div class="summary-cards">
        <div class="card">
          <div class="card-value">{{ usage.total_credits.toLocaleString() }}</div>
          <div class="card-label">Credits Used</div>
        </div>
        <div class="card">
          <div class="card-value">{{ usage.total_generations }}</div>
          <div class="card-label">Generations</div>
        </div>
        <div class="card">
          <div class="card-value">{{ usage.total_generations ? Math.round(usage.total_credits / usage.total_generations) : 0 }}</div>
          <div class="card-label">Avg per Generation</div>
        </div>
      </div>

      <!-- By Model -->
      <section class="usage-section">
        <h2>By Model</h2>
        <div class="model-grid">
          <div v-for="(info, model) in usage.by_model" :key="model" class="model-row">
            <div class="model-name">{{ info.label }}</div>
            <div class="model-stats">
              <span class="model-credits">{{ info.credits.toLocaleString() }} credits</span>
              <span class="model-count">{{ info.count }} gen{{ info.count !== 1 ? 's' : '' }}</span>
            </div>
            <div class="model-bar">
              <div class="model-bar-fill" :style="{ width: barWidth(info.credits) }"></div>
            </div>
          </div>
        </div>
      </section>

      <!-- By Project (top 10) - expandable -->
      <section v-if="usage.by_project.length" class="usage-section">
        <h2>Top Projects</h2>
        <div class="project-grid">
          <div v-for="item in usage.by_project" :key="item.project" class="project-block">
            <div class="project-row" @click="toggleProject(item.project)">
              <span class="project-expand">{{ expandedProjects[item.project] ? '▾' : '▸' }}</span>
              <router-link :to="`/project/${item.project}/gallery`" class="project-link" @click.stop>
                {{ item.project }}
              </router-link>
              <span class="project-gen-counts">
                <span class="gen-total">{{ item.total }} gen{{ item.total !== 1 ? 's' : '' }}</span>
                <span v-if="item.done" class="gen-done">{{ item.done }} ✓</span>
                <span v-if="item.error" class="gen-error">{{ item.error }} ✗</span>
              </span>
              <span class="project-credits">{{ item.credits.toLocaleString() }} credits</span>
            </div>
            <!-- Expanded generation details -->
            <div v-if="expandedProjects[item.project]" class="project-details">
              <div v-if="projectLoading[item.project]" class="project-details-loading">Loading...</div>
              <div v-else-if="projectJobs[item.project]?.length" class="project-jobs-list">
                <div v-for="job in projectJobs[item.project]" :key="job.job_id" class="project-job-row">
                  <div class="project-job-thumb">
                    <img v-if="getThumbUrl(item.project, job)" :src="getThumbUrl(item.project, job)" alt="" />
                    <div v-else class="project-job-thumb-placeholder" :class="job.status"></div>
                  </div>
                  <div class="project-job-info">
                    <span class="project-job-model">{{ job.model }}</span>
                    <span class="project-job-date">{{ formatDateTime(job.created_at) }}</span>
                    <span v-if="job.message" class="project-job-msg">{{ job.message }}</span>
                  </div>
                  <span :class="['project-job-status', job.status]">{{ job.status }}</span>
                  <span class="project-job-credits">{{ job.credits_used }} cr</span>
                </div>
              </div>
              <div v-else class="project-details-loading">No generations found</div>
            </div>
          </div>
        </div>
      </section>

      <!-- Daily Chart (text-based) -->
      <section v-if="usage.by_day.length" class="usage-section">
        <h2>Daily Usage</h2>
        <div class="daily-grid">
          <div v-for="[day, credits] in usage.by_day" :key="day" class="daily-row">
            <span class="daily-date">{{ formatDate(day) }}</span>
            <div class="daily-bar">
              <div class="daily-bar-fill" :style="{ width: dayBarWidth(credits) }"></div>
            </div>
            <span class="daily-credits">{{ credits }}</span>
          </div>
        </div>
      </section>
    </template>
  </div>
</template>


<style scoped>
.usage-view {
  max-width: 800px;
  margin: 0 auto;
  padding: 2rem 1.5rem;
}

.usage-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 2rem;
}

.usage-header h1 {
  font-size: 1.5rem;
  font-weight: 600;
}

.period-selector {
  display: flex;
  gap: 0.5rem;
}

.period-selector button {
  padding: 0.4rem 0.8rem;
  border-radius: 6px;
  border: 1px solid var(--border-color, #333);
  background: transparent;
  color: var(--text-color, #eee);
  cursor: pointer;
  font-size: 0.85rem;
  transition: all 0.15s;
}

.period-selector button.active {
  background: var(--accent-color, #6366f1);
  border-color: var(--accent-color, #6366f1);
  color: #fff;
}

.period-selector button:hover:not(.active) {
  border-color: var(--accent-color, #6366f1);
}

.summary-cards {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 1rem;
  margin-bottom: 2rem;
}

.balance-card {
  background: linear-gradient(135deg, var(--accent-color, #6366f1) 0%, #8b5cf6 100%);
  border-radius: 12px;
  padding: 1.5rem;
  margin-bottom: 1.5rem;
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.balance-available {
  display: flex;
  align-items: baseline;
  gap: 0.5rem;
}

.balance-value {
  font-size: 2rem;
  font-weight: 700;
  color: #fff;
}

.balance-label {
  font-size: 0.9rem;
  color: rgba(255, 255, 255, 0.8);
}

.balance-total {
  font-size: 0.85rem;
  color: rgba(255, 255, 255, 0.6);
}

.card {
  background: var(--bg-card, #1a1a2e);
  border: 1px solid var(--border-color, #333);
  border-radius: 10px;
  padding: 1.25rem;
  text-align: center;
}

.card-value {
  font-size: 1.75rem;
  font-weight: 700;
  color: var(--accent-color, #6366f1);
}

.card-label {
  font-size: 0.8rem;
  color: var(--text-secondary, #888);
  margin-top: 0.25rem;
}

.usage-section {
  margin-bottom: 2rem;
}

.usage-section h2 {
  font-size: 1.1rem;
  font-weight: 600;
  margin-bottom: 0.75rem;
}

.model-grid, .project-grid, .daily-grid {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.model-row {
  display: grid;
  grid-template-columns: 180px 1fr;
  grid-template-rows: auto auto;
  gap: 0.25rem 1rem;
  align-items: center;
  padding: 0.5rem 0;
  border-bottom: 1px solid var(--border-color, #222);
}

.model-name {
  font-weight: 500;
  font-size: 0.9rem;
}

.model-stats {
  display: flex;
  gap: 1rem;
  font-size: 0.8rem;
  color: var(--text-secondary, #888);
}

.model-credits {
  color: var(--accent-color, #6366f1);
  font-weight: 500;
}

.model-bar {
  grid-column: 1 / -1;
  height: 4px;
  background: var(--border-color, #222);
  border-radius: 2px;
  overflow: hidden;
}

.model-bar-fill {
  height: 100%;
  background: var(--accent-color, #6366f1);
  border-radius: 2px;
  transition: width 0.3s ease;
}

.project-row {
  display: flex;
  align-items: center;
  padding: 0.5rem 0;
  border-bottom: 1px solid var(--border-color, #222);
  cursor: pointer;
  gap: 0.5rem;
}

.project-row:hover {
  background: rgba(99, 102, 241, 0.05);
}

.project-expand {
  font-size: 0.75rem;
  color: var(--text-secondary, #888);
  width: 1rem;
  flex-shrink: 0;
}

.project-link {
  color: var(--text-color, #eee);
  text-decoration: none;
  font-size: 0.9rem;
  flex: 1;
}

.project-link:hover {
  color: var(--accent-color, #6366f1);
}

.project-credits {
  font-size: 0.85rem;
  color: var(--text-secondary, #888);
  white-space: nowrap;
}

.project-gen-counts {
  display: flex;
  gap: 6px;
  align-items: center;
  font-size: 0.75rem;
  margin-left: auto;
  margin-right: 12px;
  flex-shrink: 0;
}

.gen-total {
  color: var(--text-secondary, #888);
}

.gen-done {
  color: #22c55e;
}

.gen-error {
  color: #ef4444;
}

.project-block {
  border-bottom: 1px solid var(--border-color, #222);
}

.project-block .project-row {
  border-bottom: none;
}

.project-details {
  padding: 0.25rem 0 0.75rem 1.5rem;
}

.project-details-loading {
  font-size: 0.8rem;
  color: var(--text-secondary, #888);
  padding: 0.5rem 0;
}

.project-jobs-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.project-job-row {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 6px 8px;
  border-radius: 6px;
  background: var(--bg-card, #1a1a2e);
  border: 1px solid var(--border-color, #222);
}

.project-job-thumb {
  width: 36px;
  height: 36px;
  border-radius: 4px;
  overflow: hidden;
  flex-shrink: 0;
  background: var(--border-color, #222);
}

.project-job-thumb img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}

.project-job-thumb-placeholder {
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--border-color, #333);
}

.project-job-thumb-placeholder.done {
  background: rgba(34, 197, 94, 0.15);
}

.project-job-thumb-placeholder.error {
  background: rgba(239, 68, 68, 0.15);
}

.project-job-info {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 1px;
}

.project-job-model {
  font-size: 0.8rem;
  font-weight: 600;
}

.project-job-date {
  font-size: 0.7rem;
  color: var(--text-secondary, #888);
}

.project-job-msg {
  font-size: 0.7rem;
  color: var(--text-secondary, #666);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.project-job-status {
  font-size: 0.7rem;
  padding: 2px 6px;
  border-radius: 4px;
  background: var(--border-color, #333);
  flex-shrink: 0;
}

.project-job-status.done {
  background: rgba(34, 197, 94, 0.15);
  color: #22c55e;
}

.project-job-status.error {
  background: rgba(239, 68, 68, 0.15);
  color: #ef4444;
}

.project-job-credits {
  font-size: 0.8rem;
  font-weight: 600;
  color: var(--accent-color, #6366f1);
  white-space: nowrap;
  min-width: 40px;
  text-align: right;
}

.daily-row {
  display: grid;
  grid-template-columns: 70px 1fr 50px;
  gap: 0.75rem;
  align-items: center;
  font-size: 0.8rem;
}

.daily-date {
  color: var(--text-secondary, #888);
}

.daily-bar {
  height: 6px;
  background: var(--border-color, #222);
  border-radius: 3px;
  overflow: hidden;
}

.daily-bar-fill {
  height: 100%;
  background: var(--accent-color, #6366f1);
  border-radius: 3px;
  transition: width 0.3s ease;
}

.daily-credits {
  text-align: right;
  color: var(--text-secondary, #888);
}

.loading {
  text-align: center;
  padding: 3rem;
  color: var(--text-secondary, #888);
}

@media (max-width: 600px) {
  .summary-cards {
    grid-template-columns: 1fr;
  }
  .model-row {
    grid-template-columns: 1fr;
  }
}
</style>


<script setup>
import { provide, onMounted } from 'vue'
import AppHeader from './components/AppHeader.vue'
import ToastContainer from './components/ToastContainer.vue'
import JobsSidebar from './components/JobsSidebar.vue'
import { useToast } from './composables/useToast'
import { useJobsQueue } from './composables/useJobsQueue'
import { useSessionCredits } from './composables/useSessionCredits'

const { toasts, showToast, removeToast } = useToast()
provide('showToast', showToast)

const { activeJobs, initialize, onJobComplete, onJobError } = useJobsQueue()
const { addCredits, refreshBalance } = useSessionCredits()

// Track credits when jobs complete — subtract locally for instant feedback
onJobComplete((job) => {
  if (job.credits_used) {
    addCredits(job.credits_used)
  }
  // Also refresh from API to stay in sync
  refreshBalance(true)
})

// On failure, credits are refunded — refresh balance from API
onJobError(() => {
  refreshBalance(true)
})

// Initialize jobs queue on app load — must be here (not in sidebar)
// because the sidebar only mounts when activeJobs.length > 0.
onMounted(() => {
  initialize()
  refreshBalance()
})
</script>

<template>
  <div class="app-layout">
    <div class="main-content">
      <div class="container">
        <AppHeader />
        <router-view />
      </div>
    </div>

    <JobsSidebar v-if="activeJobs.length > 0" />
  </div>

  <ToastContainer :toasts="toasts" @remove="removeToast" />
</template>

<style>
.app-layout {
  display: flex;
  min-height: 100vh;
}

.main-content {
  flex: 1;
  min-width: 0;
}
</style>

<script setup>
import { provide, onMounted, computed } from 'vue'
import { useRoute } from 'vue-router'
import AppHeader from './components/AppHeader.vue'
import KeyModal from './components/KeyModal.vue'
import ToastContainer from './components/ToastContainer.vue'
import JobsSidebar from './components/JobsSidebar.vue'
import { useToast } from './composables/useToast'
import { useJobsQueue } from './composables/useJobsQueue'
import { useSessionCredits } from './composables/useSessionCredits'

const route = useRoute()
// Full-bleed pages (chat) own the whole viewport: no header, no container
const fullBleed = computed(() => !!route.meta.fullBleed)

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
      <router-view v-if="fullBleed" />
      <div v-else class="container">
        <AppHeader />
        <router-view />
      </div>
    </div>

    <JobsSidebar v-if="activeJobs.length > 0" />
  </div>

  <KeyModal />
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

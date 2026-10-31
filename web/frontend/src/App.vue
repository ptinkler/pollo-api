<script setup>
import { provide } from 'vue'
import LoginModal from './components/LoginModal.vue'
import ToastContainer from './components/ToastContainer.vue'
import { useToast } from './composables/useToast'

// Studio is the whole app and owns the viewport (position: fixed). App.vue is
// just the shell: the routed Studio view plus the global login + toasts.
const { toasts, showToast, removeToast } = useToast()
provide('showToast', showToast)
</script>

<template>
  <router-view />
  <LoginModal />
  <ToastContainer :toasts="toasts" @remove="removeToast" />
</template>

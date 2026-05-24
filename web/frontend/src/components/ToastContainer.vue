<script setup>

defineProps({
  toasts: { type: Array, required: true }
})

defineEmits(['remove'])

function getIcon(type) {
  return type === 'success' ? '✓' : type === 'error' ? '✗' : 'ℹ'
}
</script>

<template>
  <div class="toaster">
    <TransitionGroup name="toast">
      <div
        v-for="toast in toasts"
        :key="toast.id"
        :class="['toast', toast.type]"
        @click="$emit('remove', toast.id)"
      >
        <span class="toast-icon">{{ getIcon(toast.type) }}</span>
        <span class="toast-message">{{ toast.message }}</span>
      </div>
    </TransitionGroup>
  </div>
</template>

<style scoped>
.toaster {
  position: fixed;
  top: 20px;
  left: 50%;
  transform: translateX(-50%);
  z-index: 2000;
  display: flex;
  flex-direction: column;
  gap: 10px;
  pointer-events: none;
}

.toast {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 12px 20px;
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.4);
  display: flex;
  align-items: center;
  gap: 10px;
  pointer-events: auto;
  cursor: pointer;
}

.toast.success {
  border-color: var(--green);
}

.toast.error {
  border-color: var(--red);
}

.toast-icon {
  font-size: 1.1rem;
}

.toast-message {
  font-size: 0.9rem;
  color: var(--text);
}

.toast-enter-active {
  animation: toastIn 0.3s ease;
}

.toast-leave-active {
  animation: toastOut 0.3s ease forwards;
}

@keyframes toastIn {
  from {
    opacity: 0;
    transform: translateY(-10px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

@keyframes toastOut {
  from {
    opacity: 1;
  }
  to {
    opacity: 0;
    transform: translateY(-10px);
  }
}
</style>


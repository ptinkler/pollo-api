<script setup>
defineProps({
  toasts: { type: Array, required: true },
})

defineEmits(['remove'])

function getIcon(type) {
  return type === 'success' ? '✓' : type === 'error' ? '✗' : 'ℹ'
}
</script>

<template>
  <div class="toaster">
    <TransitionGroup name="toast">
      <div v-for="toast in toasts" :key="toast.id" :class="['toast', toast.type]" @click="$emit('remove', toast.id)">
        <span class="toast-icon">{{ getIcon(toast.type) }}</span>
        <span class="toast-message">{{ toast.message }}</span>
      </div>
    </TransitionGroup>
  </div>
</template>

<style scoped>
.toaster {
  position: fixed;
  top: 14px;
  left: 50%;
  transform: translateX(-50%);
  z-index: 2000;
  display: flex;
  flex-direction: column;
  gap: 8px;
  pointer-events: none;
}

.toast {
  background: var(--spanel2);
  border: 1px solid var(--sborder);
  border-left: 3px solid var(--sfaint);
  border-radius: var(--r);
  padding: 8px 14px;
  box-shadow: var(--shadow-pop);
  display: flex;
  align-items: center;
  gap: 10px;
  pointer-events: auto;
  cursor: pointer;
  max-width: min(520px, calc(100vw - 32px));
}

.toast.success {
  border-left-color: var(--ssuccess);
}

.toast.error {
  border-left-color: var(--sdanger);
}

.toast-icon {
  font-size: 13px;
  font-weight: 700;
  color: var(--smuted);
}

.toast.success .toast-icon {
  color: var(--ssuccess);
}

.toast.error .toast-icon {
  color: var(--sdanger);
}

.toast-message {
  font-size: 13px;
  color: var(--sfg);
}

.toast-enter-active {
  animation: toastIn 0.2s ease;
}

.toast-leave-active {
  animation: toastOut 0.2s ease forwards;
}

@keyframes toastIn {
  from {
    opacity: 0;
    transform: translateY(-8px);
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
    transform: translateY(-8px);
  }
}
</style>

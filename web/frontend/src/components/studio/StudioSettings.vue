<!-- Studio settings, shown in the center pane. Appearance is live; keys / VPN
     summarise current setup (full management wires up next). -->
<script setup>
import { ref } from 'vue'
import StudioAccount from './StudioAccount.vue'
import StudioTitleModel from './StudioTitleModel.vue'
import StudioKeys from './StudioKeys.vue'
import StudioUploads from './StudioUploads.vue'
import StudioVpnCard from './StudioVpnCard.vue'

defineProps({
  theme: { type: String, default: 'system' },
})
defineEmits(['set-theme', 'close', 'sign-out'])

// VPN controls are admin-only; StudioAccount reports the signed-in user
const isAdmin = ref(false)
function onUser(user) {
  isAdmin.value = !!(user && user.is_admin)
}

const THEMES = [
  { id: 'system', label: 'System' },
  { id: 'light', label: 'Light' },
  { id: 'dark', label: 'Dark' },
]
</script>

<template>
  <div class="page">
    <div class="pwrap narrow">
      <div class="phead">
        <h1>Settings</h1>
        <div class="hactions">
          <button class="btn" @click="$emit('close')">
            <svg class="ic"><use href="#s-chevL" /></svg> Back
          </button>
        </div>
      </div>

      <section class="scard">
        <div class="ctitle">Appearance</div>
        <div class="crow">
          <div class="clabel">Theme</div>
          <div class="seg" role="group" aria-label="Theme">
            <button v-for="t in THEMES" :key="t.id" :class="{ on: theme === t.id }" @click="$emit('set-theme', t.id)">
              {{ t.label }}
            </button>
          </div>
        </div>
      </section>

      <StudioTitleModel />

      <StudioAccount @user="onUser" @sign-out="$emit('sign-out')" />

      <StudioKeys />

      <StudioUploads />

      <StudioVpnCard v-if="isAdmin" />
    </div>
  </div>
</template>

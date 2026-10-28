<!-- Studio settings, shown in the center pane. Appearance is live; keys / VPN
     summarise current setup (full management wires up next). -->
<script setup>
import { ref } from 'vue'
import StudioAccount from './StudioAccount.vue'
import StudioKeys from './StudioKeys.vue'
import StudioVpnCard from './StudioVpnCard.vue'

defineProps({
  theme: { type: String, default: 'system' },
})
defineEmits(['set-theme', 'close', 'navigate', 'sign-out', 'defaults', 'import'])

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
// Existing utility pages, reachable from the unified shell
const TOOLS = [
  { route: 'characters', label: 'Characters' },
  { route: 'instructions', label: 'Instructions' },
  { route: 'usage', label: 'Credit usage' },
  { route: 'request-log', label: 'Request log' },
]
</script>

<template>
  <div class="settings">
    <div class="swrap">
      <div class="shead">
        <h1>Settings</h1>
        <button class="closebtn" @click="$emit('close')">
          <svg class="ic"><use href="#s-chevL" /></svg> Back to thread
        </button>
      </div>

      <section class="card">
        <div class="ctitle">Appearance</div>
        <div class="crow">
          <div class="clabel">Theme</div>
          <div class="seg">
            <button v-for="t in THEMES" :key="t.id" :class="{ on: theme === t.id }" @click="$emit('set-theme', t.id)">
              {{ t.label }}
            </button>
          </div>
        </div>
      </section>

      <StudioAccount @user="onUser" @sign-out="$emit('sign-out')" />

      <StudioKeys />

      <section class="card">
        <div class="ctitle">Tools &amp; library</div>
        <div class="links">
          <button class="link" @click="$emit('defaults')">
            <span>Default instructions &amp; characters</span>
            <svg class="ic"><use href="#s-chev" /></svg>
          </button>
          <button v-for="t in TOOLS" :key="t.route" class="link" @click="$emit('navigate', t.route)">
            <span>{{ t.label }}</span>
            <svg class="ic"><use href="#s-chev" /></svg>
          </button>
          <button class="link" @click="$emit('import')">
            <span>Import chats…</span>
            <svg class="ic"><use href="#s-chev" /></svg>
          </button>
        </div>
      </section>

      <StudioVpnCard v-if="isAdmin" />
    </div>
  </div>
</template>

<style scoped>
.settings {
  flex: 1;
  overflow-y: auto;
  padding: 32px 22px;
}
.swrap {
  max-width: 720px;
  margin: 0 auto;
}
.shead {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 22px;
}
h1 {
  font-size: 22px;
  font-weight: 650;
  letter-spacing: -0.02em;
}
.closebtn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 7px 12px;
  border: 1px solid var(--sborder);
  border-radius: 9px;
  color: var(--smuted);
  background: none;
  cursor: pointer;
}
.closebtn:hover {
  background: var(--shover);
  color: var(--sfg);
}
.card {
  border: 1px solid var(--sborder);
  background: var(--sbg);
  border-radius: 14px;
  padding: 18px 20px;
  margin-bottom: 16px;
}
.ctitle {
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--sfaint);
  font-weight: 650;
  margin-bottom: 14px;
}
.crow {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}
.clabel {
  color: var(--sfg);
}
.seg {
  display: inline-flex;
  border: 1px solid var(--sborder);
  border-radius: 10px;
  overflow: hidden;
}
.seg button {
  padding: 7px 16px;
  border: none;
  background: none;
  color: var(--smuted);
  cursor: pointer;
  font-size: 13px;
}
.seg button + button {
  border-left: 1px solid var(--sborder);
}
.seg button.on {
  background: var(--saccent-soft);
  color: var(--saccent);
}
.cnote {
  color: var(--smuted);
  line-height: 1.6;
  font-size: 13px;
  margin-top: 10px;
}
.btn {
  padding: 7px 14px;
  border: 1px solid var(--sborder);
  border-radius: 9px;
  color: var(--sfg);
  background: none;
  cursor: pointer;
}
.btn:hover {
  background: var(--shover);
}
.links {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.link {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 11px 12px;
  border: none;
  border-radius: 9px;
  background: none;
  color: var(--sfg);
  cursor: pointer;
  font-size: 13.5px;
}
.link:hover {
  background: var(--shover);
}
.link .ic {
  color: var(--sfaint);
}
.balances {
  margin-top: 12px;
}
</style>

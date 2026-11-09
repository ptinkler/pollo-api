<!-- Settings: the user's own provider keys. Write-only — a set key shows a
     masked hint and can be replaced or cleared, never read back. -->
<script setup>
import { ref, reactive, onMounted } from 'vue'
import { fetchUserKeys, saveUserKeys, KEY_PROVIDERS } from '../../composables/useAccount'

const keys = ref({}) // { provider: { set, hint } }
const drafts = reactive({}) // provider -> new value typed (or '' to clear)
const saving = ref(false)
const message = ref('')

async function load() {
  try {
    keys.value = (await fetchUserKeys()).keys || {}
  } catch {
    keys.value = {}
  }
}

async function save() {
  saving.value = true
  message.value = ''
  const payload = {}
  for (const p of KEY_PROVIDERS) {
    if (p.id in drafts) payload[p.id] = drafts[p.id] // only what changed
  }
  try {
    keys.value = (await saveUserKeys(payload)).keys || keys.value
    for (const k of Object.keys(drafts)) delete drafts[k]
    message.value = 'Saved'
  } catch (e) {
    message.value = e.message
  } finally {
    saving.value = false
  }
}

onMounted(load)
</script>

<template>
  <section class="scard">
    <div class="ctitle">Provider keys</div>
    <p class="cnote">Enter your Pollo, Venice and OpenRouter keys.</p>
    <div class="rows">
      <div v-for="p in KEY_PROVIDERS" :key="p.id" class="krow">
        <div class="kl">
          {{ p.label }}
          <span v-if="keys[p.id]?.set" class="kset">{{ keys[p.id].hint }}</span>
        </div>
        <input
          :value="drafts[p.id] ?? ''"
          type="password"
          autocomplete="off"
          :placeholder="keys[p.id]?.set ? 'Enter a new key to replace' : 'Paste key'"
          @input="drafts[p.id] = $event.target.value"
        />
        <button v-if="keys[p.id]?.set" class="btn btn-sm" title="Clear this key" @click="drafts[p.id] = ''">
          Clear
        </button>
      </div>
    </div>
    <div class="cactions">
      <button class="btn btn-primary" :disabled="saving" @click="save">{{ saving ? 'Saving…' : 'Save keys' }}</button>
      <span v-if="message" class="cmsg">{{ message }}</span>
    </div>
  </section>
</template>

<style scoped>
.rows {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.krow {
  display: grid;
  grid-template-columns: 110px 1fr auto;
  align-items: center;
  gap: 10px;
}
.kl {
  color: var(--sfg);
  font-size: 13.5px;
  display: flex;
  align-items: center;
  gap: 8px;
}
.kset {
  font-size: 11px;
  color: var(--saccent);
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
}
</style>

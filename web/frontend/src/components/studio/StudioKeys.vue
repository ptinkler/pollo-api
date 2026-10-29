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
  <section class="card">
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
        <button v-if="keys[p.id]?.set" class="xbtn" title="Clear this key" @click="drafts[p.id] = ''">Clear</button>
      </div>
    </div>
    <div class="actions">
      <button class="btn" :disabled="saving" @click="save">{{ saving ? 'Saving…' : 'Save keys' }}</button>
      <span v-if="message" class="msg">{{ message }}</span>
    </div>
  </section>
</template>

<style scoped>
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
  margin-bottom: 12px;
}
.cnote {
  color: var(--smuted);
  line-height: 1.6;
  font-size: 13px;
  margin-bottom: 14px;
}
.rows {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.krow {
  display: grid;
  grid-template-columns: 120px 1fr auto;
  align-items: center;
  gap: 10px;
}
.kl {
  color: var(--sfg);
  display: flex;
  align-items: center;
  gap: 8px;
}
.kset {
  font-size: 11px;
  color: var(--saccent);
  font-family: monospace;
}
input {
  padding: 8px 10px;
  border: 1px solid var(--sborder);
  border-radius: 9px;
  background: var(--spanel2);
  color: var(--sfg);
  outline: none;
}
.xbtn {
  padding: 7px 11px;
  border: 1px solid var(--sborder);
  border-radius: 8px;
  color: var(--smuted);
  background: none;
  cursor: pointer;
  font-size: 12px;
}
.xbtn:hover {
  background: var(--shover);
  color: var(--sfg);
}
.actions {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-top: 16px;
}
.btn {
  padding: 8px 16px;
  border: none;
  border-radius: 9px;
  background: var(--saccent);
  color: #fff;
  cursor: pointer;
  font-weight: 600;
}
.btn:disabled {
  opacity: 0.5;
  cursor: default;
}
.msg {
  font-size: 12px;
  color: var(--smuted);
}
</style>

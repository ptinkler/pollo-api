<!-- Settings: where source media (image/audio/video) is uploaded so a URL-only
     provider (Pollo) can fetch it — a third-party temp host, or self-hosted
     from this instance. One setting covers all media kinds. -->
<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import {
  fetchUploadPrefs,
  saveUploadPrefs,
  testSelfhost,
  UPLOAD_HOSTS,
  EXPIRY_LABELS,
} from '../../composables/useAccount'

const prefs = reactive({ primary: 'litterbox', backup: null, expiry_minutes: 60, selfhost_base: '' })
const meta = reactive({ expiry_options: [60, 720, 1440, 4320], expiry_configurable: [], public_base_url_set: false })
const saving = ref(false)
const message = ref('')
const testing = ref(false)
const testResult = ref(null) // { ok, detail }

const usesSelfhost = computed(() => prefs.primary === 'selfhost' || prefs.backup === 'selfhost')
const expiryEditable = computed(() =>
  [prefs.primary, prefs.backup].some(h => h && meta.expiry_configurable.includes(h)),
)

async function load() {
  try {
    const d = await fetchUploadPrefs()
    Object.assign(prefs, d.prefs)
    Object.assign(meta, d)
  } catch {
    /* keep defaults */
  }
}

async function save() {
  saving.value = true
  message.value = ''
  try {
    const d = await saveUploadPrefs({ ...prefs, backup: prefs.backup || null })
    Object.assign(prefs, d.prefs)
    message.value = 'Saved'
  } catch (e) {
    message.value = e.message
  } finally {
    saving.value = false
  }
}

async function runTest() {
  testing.value = true
  testResult.value = null
  try {
    testResult.value = await testSelfhost(prefs.selfhost_base)
  } catch (e) {
    testResult.value = { ok: false, detail: e.message }
  } finally {
    testing.value = false
  }
}

onMounted(load)
</script>

<template>
  <section class="card">
    <div class="ctitle">Media uploads</div>
    <p class="cnote">
      Pollo only accepts a URL, so a source image, audio or video you attach is hosted somewhere public first for Pollo
      to fetch. Choose where. Self-host serves it from this instance instead of a third-party temp host.
    </p>

    <div class="rows">
      <div class="urow">
        <label class="ul">Primary host</label>
        <select v-model="prefs.primary">
          <option v-for="h in UPLOAD_HOSTS" :key="h.id" :value="h.id">{{ h.label }}</option>
        </select>
      </div>

      <div class="urow">
        <label class="ul">Backup host</label>
        <select v-model="prefs.backup">
          <option :value="null">None</option>
          <option v-for="h in UPLOAD_HOSTS" :key="h.id" :value="h.id" :disabled="h.id === prefs.primary">
            {{ h.label }}
          </option>
        </select>
      </div>

      <div class="urow">
        <label class="ul">Keep for</label>
        <select v-model.number="prefs.expiry_minutes" :disabled="!expiryEditable">
          <option v-for="m in meta.expiry_options" :key="m" :value="m">{{ EXPIRY_LABELS[m] || m + ' min' }}</option>
        </select>
        <span v-if="!expiryEditable" class="hint">Fixed by the selected host</span>
      </div>

      <div v-if="usesSelfhost" class="urow selfhost">
        <label class="ul">Self-host URL</label>
        <input
          v-model="prefs.selfhost_base"
          type="url"
          placeholder="https://your-host.example.com"
          autocomplete="off"
        />
        <button class="xbtn" :disabled="testing || !prefs.selfhost_base" @click="runTest">
          {{ testing ? 'Testing…' : 'Test' }}
        </button>
      </div>
      <p v-if="usesSelfhost" class="subnote">
        The public https address this instance is reachable at — Pollo fetches source media from
        <code>&lt;url&gt;/api/public-media/…</code> via a signed, expiring link.
        <span v-if="!meta.public_base_url_set"> (No <code>PUBLIC_BASE_URL</code> set, so this must be filled in.)</span>
      </p>
      <p v-if="testResult" class="subnote" :class="{ ok: testResult.ok, bad: !testResult.ok }">
        {{ testResult.ok ? '✓ ' : '✗ ' }}{{ testResult.detail }}
      </p>
    </div>

    <div class="actions">
      <button class="btn" :disabled="saving" @click="save">{{ saving ? 'Saving…' : 'Save' }}</button>
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
.urow {
  display: grid;
  grid-template-columns: 120px 1fr auto;
  align-items: center;
  gap: 10px;
}
.ul {
  color: var(--sfg);
}
select,
input {
  padding: 8px 10px;
  border: 1px solid var(--sborder);
  border-radius: 9px;
  background: var(--spanel2);
  color: var(--sfg);
  outline: none;
}
select:disabled {
  opacity: 0.5;
}
.hint {
  font-size: 11px;
  color: var(--sfaint);
}
.subnote {
  font-size: 12px;
  color: var(--smuted);
  line-height: 1.5;
  margin: 2px 0 0;
}
.subnote code {
  font-family: monospace;
  font-size: 11px;
}
.subnote.ok {
  color: #3fcabf;
}
.subnote.bad {
  color: #ff8a6e;
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
.xbtn:hover:not(:disabled) {
  background: var(--shover);
  color: var(--sfg);
}
.xbtn:disabled {
  opacity: 0.5;
  cursor: default;
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

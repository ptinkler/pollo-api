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
// Fallback mirrors the backend (web/upload_settings.py) so the form behaves
// sanely before the fetch lands or if it fails — litterbox/selfhost retention
// is user-settable, so don't default "Keep for" to locked.
const meta = reactive({
  expiry_options: [60, 720, 1440, 4320],
  expiry_configurable: ['litterbox', 'selfhost'],
  public_base_url_set: false,
})
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
  <section class="scard">
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
        <button class="btn btn-sm" :disabled="testing || !prefs.selfhost_base" @click="runTest">
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

    <div class="cactions">
      <button class="btn btn-primary" :disabled="saving" @click="save">{{ saving ? 'Saving…' : 'Save' }}</button>
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
.urow {
  display: grid;
  grid-template-columns: 110px 1fr auto;
  align-items: center;
  gap: 10px;
}
.ul {
  color: var(--sfg);
  font-size: 13.5px;
  text-transform: none;
  letter-spacing: 0;
  font-weight: 400;
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
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 11px;
}
.subnote.ok {
  color: var(--ssuccess);
}
.subnote.bad {
  color: var(--sdanger);
}
</style>

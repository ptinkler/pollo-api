<!-- Credit usage / balances for every provider, shown in the center pane.
     Balances come from the shared studio state; key status is fetched here.
     Replaces the old project-centric /usage page. -->
<script setup>
import { ref, computed, onMounted } from 'vue'
import { fetchUserKeys } from '../../composables/useAccount'

const props = defineProps({
  // { pollo, openrouter, venice, veniceCredits } — nulls show as —
  balances: { type: Object, default: () => ({}) },
})
const emit = defineEmits(['close', 'manage-keys', 'refresh'])

const keys = ref({})
const loading = ref(true)
async function loadKeys() {
  loading.value = true
  try {
    keys.value = (await fetchUserKeys()).keys || {}
  } catch {
    keys.value = {}
  } finally {
    loading.value = false
  }
}
onMounted(loadKeys)

const fmtCredits = v => (v == null ? '—' : Math.round(v).toLocaleString())
const fmtBal = v => (v == null ? '—' : `$${v.toFixed(2)}`)

const providers = computed(() => [
  {
    id: 'pollo',
    label: 'Pollo',
    unit: 'credits',
    value: fmtCredits(props.balances.pollo),
    note: 'Image & video generation',
  },
  {
    id: 'openrouter',
    label: 'OpenRouter',
    unit: 'balance',
    value: fmtBal(props.balances.openrouter),
    note: 'Chat / text models',
  },
  {
    id: 'venice',
    label: 'Venice',
    unit: 'balance',
    value: fmtBal(props.balances.venice),
    note: props.balances.veniceCredits != null ? `${props.balances.veniceCredits} plan credits` : 'Chat & media',
  },
])
function keySet(id) {
  return !!keys.value[id]?.set
}
</script>

<template>
  <div class="usage">
    <div class="uwrap">
      <div class="uhead">
        <h1>Credit usage</h1>
        <div class="uactions">
          <button class="ubtn" title="Refresh balances" @click="emit('refresh')">Refresh</button>
          <button class="closebtn" @click="emit('close')">
            <svg class="ic"><use href="#s-chevL" /></svg> Back
          </button>
        </div>
      </div>

      <div class="cards">
        <div v-for="p in providers" :key="p.id" class="pcard" :class="{ nokey: !keySet(p.id) }">
          <div class="pcard-head">
            <span class="pname">{{ p.label }}</span>
            <span class="pkey" :class="{ on: keySet(p.id) }">{{
              loading ? '' : keySet(p.id) ? 'key set' : 'no key'
            }}</span>
          </div>
          <div class="pval">{{ p.value }}</div>
          <div class="punit">{{ p.unit }}</div>
          <div class="pnote">{{ p.note }}</div>
          <button v-if="!loading && !keySet(p.id)" class="plink" @click="emit('manage-keys')">Add a key →</button>
        </div>
      </div>

      <button class="manage" @click="emit('manage-keys')">Manage provider keys</button>
    </div>
  </div>
</template>

<style scoped>
.usage {
  flex: 1;
  overflow-y: auto;
  padding: 32px 22px;
}
.uwrap {
  max-width: 720px;
  margin: 0 auto;
}
.uhead {
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
.uactions {
  display: flex;
  gap: 8px;
}
.ubtn,
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
.ubtn:hover,
.closebtn:hover {
  background: var(--shover);
  color: var(--sfg);
}
.cards {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(190px, 1fr));
  gap: 14px;
  margin-bottom: 18px;
}
.pcard {
  border: 1px solid var(--sborder);
  background: var(--sbg);
  border-radius: 14px;
  padding: 18px;
}
.pcard.nokey {
  opacity: 0.75;
}
.pcard-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 10px;
}
.pname {
  font-weight: 600;
}
.pkey {
  font-size: 11px;
  padding: 2px 7px;
  border-radius: 999px;
  color: var(--smuted);
  background: var(--sbg2);
}
.pkey.on {
  color: var(--saccent);
  background: var(--saccent-soft);
}
.pval {
  font-size: 28px;
  font-weight: 700;
  color: var(--sfg);
}
.punit {
  font-size: 12px;
  color: var(--sfaint);
}
.pnote {
  margin-top: 8px;
  font-size: 12px;
  color: var(--smuted);
}
.plink {
  margin-top: 12px;
  padding: 6px 10px;
  border: 1px solid var(--saccent);
  border-radius: 8px;
  background: none;
  color: var(--saccent);
  cursor: pointer;
  font-size: 12px;
}
.manage {
  padding: 9px 14px;
  border: 1px solid var(--sborder);
  border-radius: 10px;
  background: none;
  color: var(--sfg);
  cursor: pointer;
}
.manage:hover {
  background: var(--shover);
}
</style>

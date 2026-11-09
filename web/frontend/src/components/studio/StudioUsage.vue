<!-- Credit usage / balances for every provider, shown in the center pane.
     Balances come from the shared studio state; key status is fetched here.
     Replaces the old project-centric /usage page. -->
<script setup>
import { ref, computed, onMounted } from 'vue'
import { fetchUserKeys } from '../../composables/useAccount'
import { fetchSpendBreakdown } from '../../composables/useChat'
import { fmtCost, creditsToUsd, shortModel } from '../../utils/format'

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

// What the money went on, per model, over a chosen period (Pollo credits are
// converted to dollars so every provider adds up)
const PERIODS = [
  { days: 7, label: '7 days' },
  { days: 30, label: '30 days' },
  { days: 0, label: 'All time' },
]
const days = ref(30)
const breakdown = ref(null)
async function loadBreakdown() {
  try {
    breakdown.value = await fetchSpendBreakdown(days.value)
  } catch {
    breakdown.value = null
  }
}
function setDays(d) {
  days.value = d
  loadBreakdown()
}
onMounted(() => {
  loadKeys()
  loadBreakdown()
})

const fmtCredits = v => (v == null ? '—' : Math.round(v).toLocaleString())
const fmtBal = v => (v == null ? '—' : `$${v.toFixed(2)}`)

const providers = computed(() => [
  {
    id: 'pollo',
    label: 'Pollo',
    unit: 'balance',
    value: props.balances.pollo == null ? '—' : fmtBal(creditsToUsd(props.balances.pollo)),
    note: `${fmtCredits(props.balances.pollo)} credits · image & video generation`,
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

      <div class="bd">
        <div class="bd-head">
          <h2>Where it went</h2>
          <div class="bd-periods">
            <button v-for="p in PERIODS" :key="p.days" :class="{ on: days === p.days }" @click="setDays(p.days)">
              {{ p.label }}
            </button>
          </div>
        </div>
        <p v-if="!breakdown" class="bd-none">Couldn't load the breakdown.</p>
        <p v-else-if="!breakdown.rows.length" class="bd-none">Nothing spent in this period.</p>
        <table v-else class="bd-table">
          <thead>
            <tr>
              <th>Model</th>
              <th>Kind</th>
              <th class="num">Items</th>
              <th class="num">Spent</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="r in breakdown.rows" :key="r.model + r.kind">
              <td>{{ shortModel(r.model) }}</td>
              <td>{{ r.kind }}</td>
              <td class="num">{{ r.count }}</td>
              <td class="num">
                {{ fmtCost(r.usd) }}<span v-if="r.credits" class="bd-cr"> · {{ r.credits }} cr</span>
              </td>
            </tr>
          </tbody>
          <tfoot>
            <tr>
              <td colspan="3">Total</td>
              <td class="num">{{ fmtCost(breakdown.total_usd) }}</td>
            </tr>
          </tfoot>
        </table>
      </div>

      <button class="manage" @click="emit('manage-keys')">Manage provider keys</button>
    </div>
  </div>
</template>

<style scoped>
.bd {
  margin-bottom: 18px;
}
.bd-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 10px;
}
.bd-head h2 {
  font-size: 15px;
  font-weight: 650;
}
.bd-periods {
  display: flex;
  gap: 6px;
}
.bd-periods button {
  padding: 5px 11px;
  border: 1px solid var(--sborder);
  border-radius: 8px;
  background: none;
  color: var(--smuted);
  cursor: pointer;
  font-size: 12px;
}
.bd-periods button.on {
  background: var(--saccent-soft);
  color: var(--saccent);
  border-color: transparent;
}
.bd-none {
  color: var(--smuted);
  font-size: 13px;
}
.bd-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}
.bd-table th,
.bd-table td {
  padding: 7px 8px;
  text-align: left;
  border-bottom: 1px solid var(--sborder2);
}
.bd-table th {
  color: var(--smuted);
  font-weight: 500;
  font-size: 12px;
}
.bd-table .num {
  text-align: right;
  font-variant-numeric: tabular-nums;
}
.bd-table tfoot td {
  font-weight: 650;
  border-bottom: 0;
}
.bd-cr {
  color: var(--sfaint);
}
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

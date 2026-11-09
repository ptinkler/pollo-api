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
  <div class="page">
    <div class="pwrap narrow">
      <div class="phead">
        <h1>Credit usage</h1>
        <div class="hactions">
          <button class="btn" title="Refresh balances" @click="emit('refresh')">
            <svg class="ic"><use href="#s-refresh" /></svg> Refresh
          </button>
          <button class="btn" @click="emit('close')">
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
          <button v-if="!loading && !keySet(p.id)" class="btn btn-sm plink" @click="emit('manage-keys')">
            Add a key
          </button>
        </div>
      </div>

      <div class="bd">
        <div class="bd-head">
          <h2>Where it went</h2>
          <div class="seg" role="group" aria-label="Period">
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

      <button class="btn" @click="emit('manage-keys')">Manage provider keys</button>
    </div>
  </div>
</template>

<style scoped>
.cards {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 10px;
  margin-bottom: 18px;
}
.pcard {
  border: 1px solid var(--sborder);
  background: var(--sbg);
  border-radius: var(--r-lg);
  padding: 14px 16px;
}
.pcard.nokey {
  opacity: 0.75;
}
.pcard-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}
.pname {
  font-weight: 600;
  font-size: 13.5px;
}
.pkey {
  font-size: 11px;
  padding: 1px 7px;
  border-radius: 999px;
  color: var(--smuted);
  background: var(--sbg2);
}
.pkey.on {
  color: var(--saccent);
  background: var(--saccent-soft);
}
.pval {
  font-size: 26px;
  font-weight: 700;
  line-height: 1.1;
  color: var(--sfg);
  font-variant-numeric: tabular-nums;
}
.punit {
  font-size: 12px;
  color: var(--sfaint);
}
.pnote {
  margin-top: 6px;
  font-size: 12px;
  color: var(--smuted);
}
.plink {
  margin-top: 10px;
  color: var(--saccent);
  border-color: var(--saccent);
}
.bd {
  margin-bottom: 18px;
}
.bd-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}
.bd-head h2 {
  font-size: 14px;
  font-weight: 650;
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
  padding: 6px 8px;
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
</style>

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

// A row's share of the biggest spender, drawn as a faint bar behind the model
// name so the shape of the spend reads without squinting at the numbers.
const topSpend = computed(() => Math.max(...(breakdown.value?.rows || []).map(r => r.usd), 0))
const share = usd => `${topSpend.value > 0 ? Math.max(1.5, (usd / topSpend.value) * 100) : 0}%`
</script>

<template>
  <div class="page">
    <div class="pwrap narrow">
      <div class="phead">
        <h1>Credit usage</h1>
        <div class="hactions">
          <button class="btn btn-icon" title="Refresh balances" aria-label="Refresh balances" @click="emit('refresh')">
            <svg class="ic"><use href="#s-refresh" /></svg>
          </button>
          <button class="btn" @click="emit('close')">
            <svg class="ic"><use href="#s-chevL" /></svg> Back
          </button>
        </div>
      </div>

      <div class="cards">
        <div
          v-for="p in providers"
          :key="p.id"
          class="pcard"
          :class="{ nokey: !keySet(p.id) }"
          :style="{ '--tint': `var(--p-${p.id})` }"
        >
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
              <td class="bd-model">
                <span class="bar" :style="{ width: share(r.usd) }"></span>
                <span class="bd-name">{{ shortModel(r.model) }}</span>
              </td>
              <td>
                <span class="kpill" :class="r.kind">{{ r.kind }}</span>
              </td>
              <td class="num">{{ r.count }}</td>
              <!-- Credits lead so the dollar amounts stay flush with the column -->
              <td class="num">
                <span v-if="r.credits" class="bd-cr">{{ r.credits }} cr · </span>{{ fmtCost(r.usd) }}
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
/* Each card wears its provider's pastel (--tint, set inline from --p-<id>):
   a soft wash, a tinted top edge and a tinted number, so the three read apart
   at a glance and match the provider tags in the model picker. */
.pcard {
  position: relative;
  overflow: hidden;
  border: 1px solid color-mix(in srgb, var(--tint) 26%, var(--sborder));
  background: linear-gradient(160deg, color-mix(in srgb, var(--tint) 11%, transparent), transparent 62%), var(--sbg);
  border-radius: var(--r-lg);
  padding: 14px 16px;
}
.pcard::before {
  content: '';
  position: absolute;
  inset: 0 0 auto;
  height: 3px;
  background: var(--tint);
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
  color: var(--tint);
  background: color-mix(in srgb, var(--tint) 16%, transparent);
}
.pval {
  font-size: 26px;
  font-weight: 700;
  line-height: 1.1;
  color: var(--tint);
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
  color: var(--tint);
  border-color: color-mix(in srgb, var(--tint) 55%, transparent);
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
.bd-model {
  position: relative;
}
.bd-model .bar {
  position: absolute;
  left: 0;
  top: 4px;
  bottom: 4px;
  border-radius: 3px;
  background: color-mix(in srgb, var(--p-pollo) 15%, transparent);
}
.bd-name {
  position: relative;
}
/* One pastel per kind of thing bought, from the provider palette */
.kpill {
  display: inline-block;
  padding: 1px 8px;
  border-radius: 999px;
  font-size: 11px;
  text-transform: capitalize;
  color: var(--k);
  background: color-mix(in srgb, var(--k) 15%, transparent);
  --k: var(--smuted);
}
.kpill.chat {
  --k: var(--p-openrouter);
}
.kpill.image {
  --k: var(--p-pollo);
}
.kpill.video {
  --k: var(--p-venice);
}
.kpill.audio {
  --k: var(--sstar);
}
</style>

<!-- Settings: the signed-in account (OAuth profile + sign out) or provider
     sign-in buttons. Emits the loaded user so Settings can gate admin-only UI. -->
<script setup>
import { ref, onMounted } from 'vue'
import { fetchAuthProviders, authLoginUrl, PROVIDER_LABELS } from '../../composables/useAccount'

const emit = defineEmits(['user', 'sign-out'])

const user = ref(null)
const providers = ref([])

async function load() {
  try {
    const d = await fetchAuthProviders()
    user.value = d.user
    providers.value = d.providers || []
    emit('user', d.user)
  } catch {
    user.value = null
  }
}

onMounted(load)
</script>

<template>
  <section class="scard">
    <div class="ctitle">Account</div>
    <div v-if="user" class="who">
      <img v-if="user.avatar_url" :src="user.avatar_url" class="av" alt="" />
      <div v-else class="av ph">{{ (user.name || user.email || '?').charAt(0).toUpperCase() }}</div>
      <div class="meta">
        <div class="nm">{{ user.name || user.email }} <span v-if="user.is_admin" class="badge admin">Admin</span></div>
        <div class="em">{{ user.email }} · {{ PROVIDER_LABELS[user.provider] || user.provider }}</div>
      </div>
      <button class="btn" @click="$emit('sign-out')">Sign out</button>
    </div>
    <template v-else>
      <div class="providers">
        <a v-for="p in providers" :key="p" class="btn" :href="authLoginUrl(p)"
          >Continue with {{ PROVIDER_LABELS[p] || p }}</a
        >
      </div>
      <p v-if="!providers.length" class="cnote">No sign-in providers configured.</p>
    </template>
  </section>
</template>

<style scoped>
.who {
  display: flex;
  align-items: center;
  gap: 12px;
}
.av {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  object-fit: cover;
  flex: 0 0 auto;
}
.av.ph {
  display: grid;
  place-items: center;
  background: var(--saccent-soft);
  color: var(--saccent);
  font-weight: 650;
}
.meta {
  flex: 1;
  min-width: 0;
}
.nm {
  color: var(--sfg);
  font-weight: 550;
  font-size: 13.5px;
  display: flex;
  align-items: center;
  gap: 8px;
}
.badge.admin {
  font-size: 10px;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  background: var(--saccent-soft);
  color: var(--saccent);
  font-weight: 650;
}
.em {
  color: var(--smuted);
  font-size: 12.5px;
  margin-top: 1px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.providers {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.providers .btn {
  justify-content: center;
}
</style>

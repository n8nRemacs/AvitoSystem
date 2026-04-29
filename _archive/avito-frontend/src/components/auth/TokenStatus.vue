<script setup>
import { computed } from 'vue'
import { useAuthStore } from '../../stores/auth'

const authStore = useAuthStore()

const ttlPercent = computed(() => {
  if (!authStore.session?.ttl_seconds) return 0
  // Assuming 24h token, calculate percentage
  const maxTtl = 24 * 3600
  return Math.max(0, Math.min(100, (authStore.session.ttl_seconds / maxTtl) * 100))
})

const ttlColor = computed(() => {
  const p = ttlPercent.value
  if (p > 50) return 'bg-green-500'
  if (p > 20) return 'bg-yellow-500'
  return 'bg-red-500'
})

async function handleDelete() {
  if (confirm('Delete active session?')) {
    await authStore.deleteSession()
  }
}
</script>

<template>
  <div class="bg-avito-sidebar rounded-xl p-5 border border-gray-700/50">
    <h3 class="text-sm font-semibold text-gray-400 uppercase tracking-wider mb-3">Session Status</h3>

    <div v-if="authStore.session?.is_active" class="space-y-3">
      <div class="flex items-center justify-between">
        <div class="flex items-center gap-3">
          <div class="w-3 h-3 rounded-full bg-green-500 animate-pulse" />
          <span class="text-white font-medium">Active</span>
          <span class="text-gray-400 text-sm">User: {{ authStore.session.user_id }}</span>
          <span class="text-gray-400 text-sm">TTL: {{ authStore.session.ttl_human }}</span>
        </div>
        <div class="flex items-center gap-2">
          <span class="text-xs text-gray-500">{{ authStore.session.source }}</span>
          <button @click="handleDelete" class="text-xs text-red-400 hover:text-red-300 px-2 py-1 rounded hover:bg-red-900/20">
            Delete
          </button>
        </div>
      </div>

      <!-- TTL progress bar -->
      <div class="h-2 bg-gray-700 rounded-full overflow-hidden">
        <div class="h-full rounded-full transition-all duration-500" :class="ttlColor" :style="{ width: ttlPercent + '%' }" />
      </div>

      <div class="flex justify-between text-xs text-gray-500">
        <span>Device: {{ authStore.session.device_id || 'N/A' }}</span>
        <span>Fingerprint: {{ authStore.session.fingerprint_preview || 'N/A' }}</span>
      </div>
    </div>

    <div v-else class="text-gray-500 text-sm">
      No active session. Upload tokens or authorize through browser.
    </div>
  </div>
</template>

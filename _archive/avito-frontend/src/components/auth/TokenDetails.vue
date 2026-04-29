<script setup>
import { ref, onMounted } from 'vue'
import { useAuthStore } from '../../stores/auth'

const authStore = useAuthStore()
const expanded = ref(false)

onMounted(() => {
  authStore.fetchTokenDetails()
})
</script>

<template>
  <div v-if="authStore.tokenDetails" class="bg-avito-sidebar rounded-xl p-5 border border-gray-700/50">
    <div class="flex items-center justify-between mb-3">
      <h3 class="text-sm font-semibold text-gray-400 uppercase tracking-wider">Token Details</h3>
      <button @click="expanded = !expanded" class="text-xs text-gray-400 hover:text-white">
        {{ expanded ? 'Collapse' : 'Expand' }}
      </button>
    </div>

    <div class="grid grid-cols-2 gap-3 text-sm">
      <div>
        <span class="text-gray-500">Algorithm:</span>
        <span class="text-white ml-2">{{ authStore.tokenDetails.header?.alg }}</span>
      </div>
      <div>
        <span class="text-gray-500">User ID:</span>
        <span class="text-white ml-2">{{ authStore.tokenDetails.user_id }}</span>
      </div>
      <div>
        <span class="text-gray-500">Issued:</span>
        <span class="text-white ml-2">{{ authStore.tokenDetails.issued_at }}</span>
      </div>
      <div>
        <span class="text-gray-500">Expires:</span>
        <span class="text-white ml-2">{{ authStore.tokenDetails.expires_at }}</span>
      </div>
      <div>
        <span class="text-gray-500">Expired:</span>
        <span class="ml-2" :class="authStore.tokenDetails.is_expired ? 'text-red-400' : 'text-green-400'">
          {{ authStore.tokenDetails.is_expired ? 'Yes' : 'No' }}
        </span>
      </div>
      <div>
        <span class="text-gray-500">TTL:</span>
        <span class="text-white ml-2">{{ authStore.tokenDetails.ttl_seconds }}s</span>
      </div>
    </div>

    <div v-if="expanded" class="mt-4">
      <h4 class="text-xs text-gray-500 mb-2">Raw Payload</h4>
      <pre class="bg-avito-dark p-3 rounded-lg text-xs text-gray-300 overflow-x-auto">{{ JSON.stringify(authStore.tokenDetails.payload, null, 2) }}</pre>
    </div>
  </div>
</template>

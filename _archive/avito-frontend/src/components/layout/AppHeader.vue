<script setup>
import { ref, onMounted } from 'vue'
import { useAuthStore } from '../../stores/auth'
import { useTenantStore } from '../../stores/tenant'

const authStore = useAuthStore()
const tenant = useTenantStore()
const apiKeyInput = ref('')
const showKeyModal = ref(false)

onMounted(() => {
  const saved = localStorage.getItem('x-api-key')
  if (saved) {
    apiKeyInput.value = saved
    authStore.fetchStatus()
  }
})

function saveApiKey() {
  localStorage.setItem('x-api-key', apiKeyInput.value)
  showKeyModal.value = false
  authStore.fetchStatus()
}
</script>

<template>
  <header class="h-14 bg-avito-sidebar border-b border-gray-700/50 flex items-center justify-between px-6">
    <!-- Session status -->
    <div class="flex items-center gap-3">
      <div
        class="w-2.5 h-2.5 rounded-full"
        :class="authStore.session?.is_active ? 'bg-green-500' : 'bg-red-500'"
      />
      <span class="text-sm text-gray-300" v-if="authStore.session?.is_active">
        User: {{ authStore.session.user_id }} | TTL: {{ authStore.session.ttl_human }}
      </span>
      <span class="text-sm text-gray-500" v-else-if="tenant.isAuthenticated">
        {{ tenant.userName }}
      </span>
      <span class="text-sm text-gray-500" v-else>No active session</span>
    </div>

    <!-- API Key -->
    <div class="flex items-center gap-3">
      <span class="text-xs text-gray-500" v-if="apiKeyInput">
        Key: {{ apiKeyInput.slice(0, 8) }}...
      </span>
      <button
        @click="showKeyModal = true"
        class="text-xs px-3 py-1.5 bg-avito-card hover:bg-blue-600/30 rounded text-gray-300 transition-colors"
      >
        API Key
      </button>
    </div>

    <!-- Modal -->
    <teleport to="body">
      <div v-if="showKeyModal" class="fixed inset-0 bg-black/60 flex items-center justify-center z-50">
        <div class="bg-avito-sidebar rounded-xl p-6 w-96 border border-gray-700/50">
          <h3 class="text-lg font-semibold mb-4">API Key</h3>
          <input
            v-model="apiKeyInput"
            type="text"
            placeholder="Enter your X-Api-Key..."
            class="w-full px-3 py-2 bg-avito-dark border border-gray-600 rounded-lg text-sm text-white focus:outline-none focus:border-blue-500"
          />
          <div class="flex justify-end gap-2 mt-4">
            <button
              @click="showKeyModal = false"
              class="px-4 py-2 text-sm text-gray-400 hover:text-white"
            >Cancel</button>
            <button
              @click="saveApiKey"
              class="px-4 py-2 text-sm bg-blue-600 hover:bg-blue-500 rounded-lg text-white"
            >Save</button>
          </div>
        </div>
      </div>
    </teleport>
  </header>
</template>

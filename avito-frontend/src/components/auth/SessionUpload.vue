<script setup>
import { ref } from 'vue'
import { useAuthStore } from '../../stores/auth'

const authStore = useAuthStore()
const jsonInput = ref('')
const source = ref('manual')
const dragOver = ref(false)
const error = ref(null)

const sources = [
  { value: 'manual', label: 'Manual' },
  { value: 'android', label: 'Android' },
  { value: 'redroid', label: 'Redroid' },
  { value: 'farm', label: 'Farm' },
]

async function handleUpload() {
  error.value = null
  try {
    const parsed = JSON.parse(jsonInput.value)
    const payload = {
      session_token: parsed.session_token || parsed.session || parsed.token,
      refresh_token: parsed.refresh_token,
      device_id: parsed.device_id || parsed.session_data?.device_id,
      fingerprint: parsed.fingerprint || parsed.fpx || parsed.session_data?.fingerprint,
      remote_device_id: parsed.remote_device_id || parsed.session_data?.remote_device_id,
      user_hash: parsed.user_hash || parsed.session_data?.user_hash,
      cookies: parsed.cookies || parsed.session_data?.cookies,
      source: source.value,
    }
    if (!payload.session_token) {
      error.value = 'Missing session_token field'
      return
    }
    await authStore.uploadSession(payload)
    jsonInput.value = ''
  } catch (e) {
    error.value = e.response?.data?.detail || e.message
  }
}

function handleDrop(e) {
  dragOver.value = false
  const file = e.dataTransfer?.files?.[0]
  if (file) {
    const reader = new FileReader()
    reader.onload = (ev) => { jsonInput.value = ev.target.result }
    reader.readAsText(file)
  }
}
</script>

<template>
  <div class="bg-avito-sidebar rounded-xl p-5 border border-gray-700/50">
    <h3 class="text-sm font-semibold text-gray-400 uppercase tracking-wider mb-3">Upload Session</h3>

    <div class="space-y-3">
      <!-- Source selector -->
      <div class="flex gap-2">
        <button
          v-for="s in sources"
          :key="s.value"
          @click="source = s.value"
          class="px-3 py-1.5 text-xs rounded-lg transition-colors"
          :class="source === s.value
            ? 'bg-blue-600 text-white'
            : 'bg-avito-dark text-gray-400 hover:text-white'"
        >{{ s.label }}</button>
      </div>

      <!-- JSON input -->
      <div
        @dragover.prevent="dragOver = true"
        @dragleave="dragOver = false"
        @drop.prevent="handleDrop"
        class="relative"
        :class="dragOver ? 'ring-2 ring-blue-500 rounded-lg' : ''"
      >
        <textarea
          v-model="jsonInput"
          rows="6"
          placeholder='{"session_token": "eyJ...", "refresh_token": "...", ...}'
          class="w-full px-3 py-2 bg-avito-dark border border-gray-600 rounded-lg text-sm text-white font-mono resize-y focus:outline-none focus:border-blue-500"
        />
        <p v-if="dragOver" class="absolute inset-0 flex items-center justify-center bg-blue-900/50 rounded-lg text-blue-200 text-sm pointer-events-none">
          Drop JSON file here
        </p>
      </div>

      <div v-if="error" class="text-red-400 text-sm">{{ error }}</div>

      <button
        @click="handleUpload"
        :disabled="!jsonInput.trim() || authStore.loading"
        class="px-4 py-2 bg-blue-600 hover:bg-blue-500 disabled:opacity-50 disabled:cursor-not-allowed rounded-lg text-sm text-white transition-colors"
      >
        {{ authStore.loading ? 'Uploading...' : 'Upload Session' }}
      </button>
    </div>
  </div>
</template>

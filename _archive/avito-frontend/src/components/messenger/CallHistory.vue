<script setup>
import { ref, onMounted } from 'vue'
import api from '../../api'

const calls = ref([])
const total = ref(0)
const loading = ref(false)

async function fetchCalls() {
  loading.value = true
  try {
    const { data } = await api.get('/calls/history')
    calls.value = data.calls || []
    total.value = data.total || 0
  } catch (e) {
    console.error('calls error:', e)
  }
  loading.value = false
}

function formatDate(iso) {
  if (!iso) return '-'
  return new Date(iso).toLocaleString('ru-RU')
}

function downloadRecording(callId) {
  const apiKey = localStorage.getItem('x-api-key')
  window.open(`/api/v1/calls/${callId}/recording?key=${apiKey}`, '_blank')
}

onMounted(fetchCalls)
</script>

<template>
  <div class="bg-avito-sidebar rounded-xl p-5 border border-gray-700/50">
    <div class="flex items-center justify-between mb-3">
      <h3 class="text-sm font-semibold text-gray-400 uppercase tracking-wider">Call History</h3>
      <span class="text-xs text-gray-500">Total: {{ total }}</span>
    </div>

    <div v-if="calls.length === 0" class="text-gray-500 text-sm">
      {{ loading ? 'Loading...' : 'No calls' }}
    </div>

    <div v-else class="overflow-x-auto">
      <table class="w-full text-sm">
        <thead>
          <tr class="text-gray-500 text-xs uppercase">
            <th class="text-left py-2 pr-4">Date</th>
            <th class="text-left py-2 pr-4">Caller</th>
            <th class="text-left py-2 pr-4">Duration</th>
            <th class="text-left py-2 pr-4">Item</th>
            <th class="text-left py-2">Recording</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="c in calls" :key="c.id" class="border-t border-gray-700/30">
            <td class="py-2 pr-4 text-gray-300">{{ formatDate(c.create_time) }}</td>
            <td class="py-2 pr-4 text-white">{{ c.caller || '-' }}</td>
            <td class="py-2 pr-4 text-gray-400">{{ c.duration || '-' }}</td>
            <td class="py-2 pr-4 text-gray-400 truncate max-w-[200px]">{{ c.item_title || '-' }}</td>
            <td class="py-2">
              <button
                v-if="c.has_record"
                @click="downloadRecording(c.id)"
                class="text-xs text-blue-400 hover:text-blue-300"
              >Download</button>
              <span v-else class="text-xs text-gray-600">-</span>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

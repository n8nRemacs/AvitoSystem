<script setup>
import { useAuthStore } from '../../stores/auth'

const authStore = useAuthStore()

function formatDate(iso) {
  if (!iso) return '-'
  return new Date(iso).toLocaleString('ru-RU')
}
</script>

<template>
  <div class="bg-avito-sidebar rounded-xl p-5 border border-gray-700/50">
    <h3 class="text-sm font-semibold text-gray-400 uppercase tracking-wider mb-3">Session History</h3>

    <div v-if="authStore.sessionHistory.length === 0" class="text-gray-500 text-sm">
      No sessions yet.
    </div>

    <div v-else class="overflow-x-auto">
      <table class="w-full text-sm">
        <thead>
          <tr class="text-gray-500 text-xs uppercase">
            <th class="text-left py-2 pr-4">Date</th>
            <th class="text-left py-2 pr-4">User ID</th>
            <th class="text-left py-2 pr-4">Source</th>
            <th class="text-left py-2 pr-4">Expires</th>
            <th class="text-left py-2">Status</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="s in authStore.sessionHistory"
            :key="s.id"
            class="border-t border-gray-700/30"
          >
            <td class="py-2 pr-4 text-gray-300">{{ formatDate(s.created_at) }}</td>
            <td class="py-2 pr-4 text-white">{{ s.user_id || '-' }}</td>
            <td class="py-2 pr-4">
              <span class="px-2 py-0.5 rounded text-xs"
                :class="{
                  'bg-green-900/30 text-green-400': s.source === 'android',
                  'bg-blue-900/30 text-blue-400': s.source === 'farm',
                  'bg-yellow-900/30 text-yellow-400': s.source === 'redroid',
                  'bg-gray-700 text-gray-300': s.source === 'manual',
                  'bg-purple-900/30 text-purple-400': s.source === 'browser',
                }"
              >{{ s.source }}</span>
            </td>
            <td class="py-2 pr-4 text-gray-400">{{ formatDate(s.expires_at) }}</td>
            <td class="py-2">
              <span v-if="s.is_active" class="text-green-400 text-xs">Active</span>
              <span v-else class="text-gray-500 text-xs">Inactive</span>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

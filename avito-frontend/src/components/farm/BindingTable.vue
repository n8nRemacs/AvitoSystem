<script setup>
import { ref } from 'vue'
import { useFarmStore } from '../../stores/farm'

const farmStore = useFarmStore()
const showAdd = ref(false)
const form = ref({
  tenant_id: '',
  farm_device_id: '',
  android_profile_id: 10,
  avito_user_id: null,
  avito_login: '',
})

async function addBinding() {
  try {
    await farmStore.createBinding(form.value)
    showAdd.value = false
    form.value = { tenant_id: '', farm_device_id: '', android_profile_id: 10, avito_user_id: null, avito_login: '' }
  } catch (e) {
    console.error('add binding error:', e)
  }
}

async function removeBinding(id) {
  if (confirm('Delete this binding?')) {
    await farmStore.deleteBinding(id)
  }
}

function statusBadge(status) {
  if (status === 'active') return 'bg-green-900/30 text-green-400'
  if (status === 'suspended') return 'bg-yellow-900/30 text-yellow-400'
  return 'bg-gray-700 text-gray-400'
}

function formatTime(iso) {
  if (!iso) return '-'
  return new Date(iso).toLocaleString('ru-RU')
}
</script>

<template>
  <div class="bg-avito-sidebar rounded-xl p-5 border border-gray-700/50">
    <div class="flex items-center justify-between mb-3">
      <h3 class="text-sm font-semibold text-gray-400 uppercase tracking-wider">Account Bindings</h3>
      <button @click="showAdd = !showAdd" class="text-xs px-3 py-1.5 bg-avito-card hover:bg-blue-600/30 rounded text-gray-300">
        + Bind account
      </button>
    </div>

    <!-- Add form -->
    <div v-if="showAdd" class="mb-4 p-3 bg-avito-dark rounded-lg space-y-2">
      <div class="flex gap-2">
        <input v-model="form.tenant_id" placeholder="Tenant ID" class="flex-1 px-3 py-2 bg-avito-sidebar border border-gray-600 rounded text-sm text-white focus:outline-none" />
        <select v-model="form.farm_device_id" class="flex-1 px-3 py-2 bg-avito-sidebar border border-gray-600 rounded text-sm text-white focus:outline-none">
          <option value="">Select device</option>
          <option v-for="d in farmStore.devices" :key="d.id" :value="d.id">{{ d.name }}</option>
        </select>
      </div>
      <div class="flex gap-2">
        <input v-model.number="form.android_profile_id" type="number" placeholder="Profile ID" class="w-32 px-3 py-2 bg-avito-sidebar border border-gray-600 rounded text-sm text-white focus:outline-none" />
        <input v-model="form.avito_login" placeholder="Avito login (phone)" class="flex-1 px-3 py-2 bg-avito-sidebar border border-gray-600 rounded text-sm text-white focus:outline-none" />
        <button @click="addBinding" class="px-4 py-2 bg-blue-600 hover:bg-blue-500 rounded text-sm text-white">Bind</button>
      </div>
    </div>

    <!-- Table -->
    <div v-if="farmStore.bindings.length === 0" class="text-gray-500 text-sm">No bindings</div>
    <div v-else class="overflow-x-auto">
      <table class="w-full text-sm">
        <thead>
          <tr class="text-gray-500 text-xs uppercase">
            <th class="text-left py-2 pr-4">Tenant</th>
            <th class="text-left py-2 pr-4">Avito User</th>
            <th class="text-left py-2 pr-4">Device</th>
            <th class="text-left py-2 pr-4">Profile</th>
            <th class="text-left py-2 pr-4">Last Refresh</th>
            <th class="text-left py-2 pr-4">Status</th>
            <th class="text-left py-2"></th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="b in farmStore.bindings" :key="b.id" class="border-t border-gray-700/30">
            <td class="py-2 pr-4 text-gray-300 text-xs font-mono">{{ b.tenant_id?.slice(0, 8) }}...</td>
            <td class="py-2 pr-4 text-white">{{ b.avito_user_id || b.avito_login || '-' }}</td>
            <td class="py-2 pr-4 text-gray-300 text-xs font-mono">{{ b.farm_device_id?.slice(0, 8) }}...</td>
            <td class="py-2 pr-4 text-gray-400">{{ b.android_profile_id }}</td>
            <td class="py-2 pr-4 text-gray-500 text-xs">{{ formatTime(b.last_refresh_at) }}</td>
            <td class="py-2 pr-4">
              <span class="px-2 py-0.5 rounded text-xs" :class="statusBadge(b.status)">{{ b.status }}</span>
            </td>
            <td class="py-2">
              <button @click="removeBinding(b.id)" class="text-xs text-red-400 hover:text-red-300">Delete</button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

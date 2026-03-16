<script setup>
import { ref } from 'vue'
import { useFarmStore } from '../../stores/farm'

const farmStore = useFarmStore()
const showAdd = ref(false)
const form = ref({ name: '', model: '', serial: '', max_profiles: 100 })

async function addDevice() {
  try {
    await farmStore.createDevice(form.value)
    showAdd.value = false
    form.value = { name: '', model: '', serial: '', max_profiles: 100 }
  } catch (e) {
    console.error('add device error:', e)
  }
}

function statusColor(status) {
  if (status === 'online') return 'bg-green-500'
  if (status === 'maintenance') return 'bg-yellow-500'
  return 'bg-red-500'
}

function formatTime(iso) {
  if (!iso) return 'Never'
  return new Date(iso).toLocaleString('ru-RU')
}
</script>

<template>
  <div class="bg-avito-sidebar rounded-xl p-5 border border-gray-700/50">
    <div class="flex items-center justify-between mb-3">
      <h3 class="text-sm font-semibold text-gray-400 uppercase tracking-wider">Farm Devices</h3>
      <button @click="showAdd = !showAdd" class="text-xs px-3 py-1.5 bg-avito-card hover:bg-blue-600/30 rounded text-gray-300">
        + Add device
      </button>
    </div>

    <!-- Add form -->
    <div v-if="showAdd" class="mb-4 p-3 bg-avito-dark rounded-lg space-y-2">
      <div class="flex gap-2">
        <input v-model="form.name" placeholder="Name" class="flex-1 px-3 py-2 bg-avito-sidebar border border-gray-600 rounded text-sm text-white focus:outline-none" />
        <input v-model="form.model" placeholder="Model" class="flex-1 px-3 py-2 bg-avito-sidebar border border-gray-600 rounded text-sm text-white focus:outline-none" />
      </div>
      <div class="flex gap-2">
        <input v-model="form.serial" placeholder="Serial" class="flex-1 px-3 py-2 bg-avito-sidebar border border-gray-600 rounded text-sm text-white focus:outline-none" />
        <input v-model.number="form.max_profiles" type="number" placeholder="Max profiles" class="w-32 px-3 py-2 bg-avito-sidebar border border-gray-600 rounded text-sm text-white focus:outline-none" />
        <button @click="addDevice" class="px-4 py-2 bg-blue-600 hover:bg-blue-500 rounded text-sm text-white">Add</button>
      </div>
    </div>

    <!-- Table -->
    <div v-if="farmStore.devices.length === 0" class="text-gray-500 text-sm">No devices registered</div>
    <div v-else class="overflow-x-auto">
      <table class="w-full text-sm">
        <thead>
          <tr class="text-gray-500 text-xs uppercase">
            <th class="text-left py-2 pr-4">Device</th>
            <th class="text-left py-2 pr-4">Model</th>
            <th class="text-left py-2 pr-4">Profiles</th>
            <th class="text-left py-2 pr-4">Status</th>
            <th class="text-left py-2">Last Heartbeat</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="d in farmStore.devices" :key="d.id" class="border-t border-gray-700/30">
            <td class="py-2 pr-4 text-white">{{ d.name }}</td>
            <td class="py-2 pr-4 text-gray-400">{{ d.model || '-' }}</td>
            <td class="py-2 pr-4 text-gray-300">{{ d.profile_count }}/{{ d.max_profiles }}</td>
            <td class="py-2 pr-4">
              <div class="flex items-center gap-2">
                <div class="w-2 h-2 rounded-full" :class="statusColor(d.status)" />
                <span class="text-gray-300 text-xs capitalize">{{ d.status }}</span>
              </div>
            </td>
            <td class="py-2 text-gray-500 text-xs">{{ formatTime(d.last_heartbeat) }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

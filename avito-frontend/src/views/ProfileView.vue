<script setup>
import { ref, onMounted } from 'vue'
import { useTenantStore } from '../stores/tenant'

const tenant = useTenantStore()

const editing = ref(false)
const editName = ref('')
const saving = ref(false)
const successMsg = ref('')

onMounted(() => {
  tenant.fetchProfile()
})

function startEdit() {
  editName.value = tenant.user?.name || ''
  editing.value = true
  successMsg.value = ''
}

function cancelEdit() {
  editing.value = false
  tenant.clearError()
}

async function saveProfile() {
  saving.value = true
  successMsg.value = ''
  try {
    await tenant.updateProfile({ name: editName.value })
    editing.value = false
    successMsg.value = 'Профиль обновлён'
    setTimeout(() => { successMsg.value = '' }, 3000)
  } catch {
    // error is set in store
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <div class="max-w-2xl mx-auto space-y-6">
    <h2 class="text-2xl font-bold text-white">Профиль</h2>

    <!-- Success -->
    <div v-if="successMsg" class="p-3 bg-green-500/10 border border-green-500/30 rounded-lg">
      <p class="text-sm text-green-400">{{ successMsg }}</p>
    </div>

    <!-- Error -->
    <div v-if="tenant.error" class="p-3 bg-red-500/10 border border-red-500/30 rounded-lg">
      <p class="text-sm text-red-400">{{ tenant.error }}</p>
    </div>

    <!-- Profile card -->
    <div class="bg-avito-sidebar rounded-xl p-6 border border-gray-700/50">
      <div class="space-y-5">
        <!-- Avatar + Name -->
        <div class="flex items-center gap-4">
          <div class="w-16 h-16 rounded-full bg-avito-card flex items-center justify-center text-2xl text-white font-bold">
            {{ (tenant.user?.name || '?')[0].toUpperCase() }}
          </div>
          <div v-if="!editing">
            <h3 class="text-xl font-semibold text-white">{{ tenant.user?.name || '---' }}</h3>
            <button @click="startEdit" class="text-xs text-blue-400 hover:text-blue-300 mt-1">Изменить</button>
          </div>
          <div v-else class="flex-1">
            <input
              v-model="editName"
              type="text"
              class="w-full px-3 py-2 bg-avito-dark border border-gray-600 rounded-lg text-white text-sm focus:outline-none focus:border-blue-500"
            />
            <div class="flex gap-2 mt-2">
              <button
                @click="saveProfile"
                :disabled="saving"
                class="px-3 py-1.5 text-xs bg-blue-600 hover:bg-blue-500 rounded-lg text-white"
              >
                {{ saving ? 'Сохранение...' : 'Сохранить' }}
              </button>
              <button @click="cancelEdit" class="px-3 py-1.5 text-xs text-gray-400 hover:text-white">Отмена</button>
            </div>
          </div>
        </div>

        <!-- Fields -->
        <div class="space-y-4 pt-4 border-t border-gray-700/50">
          <!-- Phone -->
          <div class="flex items-center justify-between">
            <div>
              <p class="text-xs text-gray-500">Телефон</p>
              <p class="text-sm text-white mt-0.5">{{ tenant.user?.phone }}</p>
            </div>
            <div class="flex items-center gap-2">
              <span v-if="tenant.user?.phone_verified" class="text-xs text-green-400">Подтверждён</span>
              <span v-else class="text-xs text-red-400">Не подтверждён</span>
            </div>
          </div>

          <!-- Email -->
          <div class="flex items-center justify-between">
            <div>
              <p class="text-xs text-gray-500">Email</p>
              <p class="text-sm text-white mt-0.5">{{ tenant.user?.email || '---' }}</p>
            </div>
            <div class="flex items-center gap-2">
              <span v-if="tenant.user?.email_verified" class="text-xs text-green-400">Подтверждён</span>
              <span v-else class="text-xs text-red-400">Не подтверждён</span>
            </div>
          </div>

          <!-- Role -->
          <div>
            <p class="text-xs text-gray-500">Роль</p>
            <p class="text-sm text-white mt-0.5 capitalize">{{ tenant.user?.role }}</p>
          </div>

          <!-- Tenant ID -->
          <div>
            <p class="text-xs text-gray-500">Tenant ID</p>
            <p class="text-sm text-gray-300 mt-0.5 font-mono text-xs">{{ tenant.user?.tenant_id }}</p>
          </div>

          <!-- Created -->
          <div>
            <p class="text-xs text-gray-500">Дата регистрации</p>
            <p class="text-sm text-white mt-0.5">
              {{ tenant.user?.created_at ? new Date(tenant.user.created_at).toLocaleDateString('ru-RU') : '---' }}
            </p>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

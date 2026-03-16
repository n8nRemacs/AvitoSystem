<script setup>
import { ref, onMounted } from 'vue'
import { useTenantStore } from '../stores/tenant'
import authApi from '../api/tenant-auth'

const tenant = useTenantStore()

const billing = ref(null)
const sessions = ref([])
const billingLoading = ref(true)

onMounted(async () => {
  await tenant.fetchProfile()
  try {
    const { data } = await authApi.get('/billing/current')
    billing.value = data
  } catch {
    // no plan assigned
  }
  try {
    const { data } = await authApi.get('/sessions')
    sessions.value = data.sessions || []
  } catch {
    // ignore
  }
  billingLoading.value = false
})
</script>

<template>
  <div class="max-w-4xl mx-auto space-y-6">
    <h2 class="text-2xl font-bold text-white">Личный кабинет</h2>

    <!-- User info card -->
    <div class="bg-avito-sidebar rounded-xl p-6 border border-gray-700/50">
      <div class="flex items-center gap-4">
        <!-- Avatar -->
        <div class="w-14 h-14 rounded-full bg-avito-card flex items-center justify-center text-xl text-white font-bold">
          {{ (tenant.user?.name || '?')[0].toUpperCase() }}
        </div>
        <div class="flex-1">
          <h3 class="text-lg font-semibold text-white">{{ tenant.user?.name || 'User' }}</h3>
          <p class="text-sm text-gray-400">{{ tenant.user?.phone }}</p>
        </div>
        <div class="text-right">
          <span class="inline-block px-2.5 py-1 text-xs rounded-full"
            :class="{
              'bg-blue-500/20 text-blue-400': tenant.user?.role === 'owner',
              'bg-green-500/20 text-green-400': tenant.user?.role === 'admin',
              'bg-yellow-500/20 text-yellow-400': tenant.user?.role === 'manager',
              'bg-gray-500/20 text-gray-400': tenant.user?.role === 'viewer',
            }"
          >
            {{ tenant.user?.role }}
          </span>
        </div>
      </div>

      <!-- Verification status -->
      <div class="flex gap-4 mt-4 pt-4 border-t border-gray-700/50">
        <div class="flex items-center gap-2">
          <div class="w-2 h-2 rounded-full" :class="tenant.user?.phone_verified ? 'bg-green-500' : 'bg-red-500'" />
          <span class="text-xs text-gray-400">Телефон {{ tenant.user?.phone_verified ? 'подтверждён' : 'не подтверждён' }}</span>
        </div>
        <div class="flex items-center gap-2">
          <div class="w-2 h-2 rounded-full" :class="tenant.user?.email_verified ? 'bg-green-500' : 'bg-red-500'" />
          <span class="text-xs text-gray-400">Email {{ tenant.user?.email_verified ? 'подтверждён' : 'не подтверждён' }}</span>
        </div>
      </div>

      <!-- Email not verified warning -->
      <div v-if="tenant.user && !tenant.user.email_verified" class="mt-4 p-3 bg-yellow-500/10 border border-yellow-500/30 rounded-lg">
        <p class="text-sm text-yellow-400">
          Подтвердите email для доступа к API-ключам и приглашению участников.
        </p>
      </div>
    </div>

    <!-- Billing -->
    <div class="bg-avito-sidebar rounded-xl p-6 border border-gray-700/50">
      <h3 class="text-lg font-semibold text-white mb-4">Тариф и лимиты</h3>

      <div v-if="billingLoading" class="text-sm text-gray-400">Загрузка...</div>

      <div v-else-if="billing">
        <div class="flex items-center gap-3 mb-4">
          <span class="text-2xl font-bold text-white capitalize">{{ billing.plan.name }}</span>
          <span class="text-sm text-gray-400">{{ billing.plan.price_monthly }} руб/мес</span>
        </div>

        <!-- Usage bars -->
        <div class="space-y-3">
          <div>
            <div class="flex justify-between text-xs text-gray-400 mb-1">
              <span>API-ключи</span>
              <span>{{ billing.usage.api_keys_used }} / {{ billing.usage.api_keys_limit }}</span>
            </div>
            <div class="h-2 bg-avito-dark rounded-full overflow-hidden">
              <div
                class="h-full bg-blue-500 rounded-full transition-all"
                :style="{ width: Math.min(100, (billing.usage.api_keys_used / billing.usage.api_keys_limit) * 100) + '%' }"
              />
            </div>
          </div>

          <div>
            <div class="flex justify-between text-xs text-gray-400 mb-1">
              <span>Сессии</span>
              <span>{{ billing.usage.sessions_used }} / {{ billing.usage.sessions_limit }}</span>
            </div>
            <div class="h-2 bg-avito-dark rounded-full overflow-hidden">
              <div
                class="h-full bg-green-500 rounded-full transition-all"
                :style="{ width: Math.min(100, (billing.usage.sessions_used / billing.usage.sessions_limit) * 100) + '%' }"
              />
            </div>
          </div>

          <div>
            <div class="flex justify-between text-xs text-gray-400 mb-1">
              <span>Пользователи</span>
              <span>{{ billing.usage.sub_users_used }} / {{ billing.usage.sub_users_limit }}</span>
            </div>
            <div class="h-2 bg-avito-dark rounded-full overflow-hidden">
              <div
                class="h-full bg-purple-500 rounded-full transition-all"
                :style="{ width: Math.min(100, (billing.usage.sub_users_used / billing.usage.sub_users_limit) * 100) + '%' }"
              />
            </div>
          </div>
        </div>
      </div>

      <div v-else class="text-sm text-gray-500">Тариф не назначен</div>
    </div>

    <!-- Active sessions -->
    <div class="bg-avito-sidebar rounded-xl p-6 border border-gray-700/50">
      <h3 class="text-lg font-semibold text-white mb-4">Активные сессии</h3>
      <div v-if="sessions.length === 0" class="text-sm text-gray-500">Нет активных сессий</div>
      <div v-else class="space-y-2">
        <div
          v-for="s in sessions"
          :key="s.id"
          class="flex items-center justify-between p-3 bg-avito-dark rounded-lg"
        >
          <div>
            <p class="text-sm text-white">{{ s.id.slice(0, 8) }}...</p>
            <p class="text-xs text-gray-500">{{ new Date(s.created_at).toLocaleString('ru-RU') }}</p>
          </div>
          <span class="text-xs text-gray-400">
            до {{ new Date(s.expires_at).toLocaleDateString('ru-RU') }}
          </span>
        </div>
      </div>
    </div>
  </div>
</template>

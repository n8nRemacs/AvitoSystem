<script setup>
import { useRouter, useRoute } from 'vue-router'
import { useTenantStore } from '../../stores/tenant'

const router = useRouter()
const route = useRoute()
const tenant = useTenantStore()

const tenantNavItems = [
  { path: '/dashboard', label: 'Dashboard', icon: '📊' },
  { path: '/profile', label: 'Профиль', icon: '👤' },
]

const panelNavItems = [
  { path: '/auth', label: 'Authorization', icon: '🔑' },
  { path: '/messenger', label: 'Messenger', icon: '💬' },
  { path: '/search', label: 'Search', icon: '🔍' },
  { path: '/farm', label: 'Token Farm', icon: '🖥️' },
]

async function handleLogout() {
  await tenant.logout()
  router.push('/login')
}
</script>

<template>
  <aside class="w-56 bg-avito-sidebar flex flex-col border-r border-gray-700/50">
    <!-- Logo -->
    <div class="p-4 border-b border-gray-700/50">
      <h1 class="text-lg font-bold text-white">Avito System</h1>
      <p class="text-xs text-gray-400 mt-1" v-if="tenant.user">{{ tenant.user.name || tenant.user.phone }}</p>
      <p class="text-xs text-gray-400 mt-1" v-else>SaaS Gateway Panel</p>
    </div>

    <!-- Tenant navigation -->
    <nav class="flex-1 p-3 space-y-1" v-if="tenant.isAuthenticated">
      <p class="px-3 py-1 text-xs text-gray-500 uppercase tracking-wider">Кабинет</p>
      <router-link
        v-for="item in tenantNavItems"
        :key="item.path"
        :to="item.path"
        class="flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm transition-colors"
        :class="route.path === item.path
          ? 'bg-avito-card text-white'
          : 'text-gray-400 hover:text-white hover:bg-gray-700/30'"
      >
        <span class="text-base">{{ item.icon }}</span>
        <span>{{ item.label }}</span>
      </router-link>

      <div class="my-3 border-t border-gray-700/30" />

      <p class="px-3 py-1 text-xs text-gray-500 uppercase tracking-wider">Avito API</p>
      <router-link
        v-for="item in panelNavItems"
        :key="item.path"
        :to="item.path"
        class="flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm transition-colors"
        :class="route.path === item.path
          ? 'bg-avito-card text-white'
          : 'text-gray-400 hover:text-white hover:bg-gray-700/30'"
      >
        <span class="text-base">{{ item.icon }}</span>
        <span>{{ item.label }}</span>
      </router-link>
    </nav>

    <!-- Not authenticated — old navigation -->
    <nav class="flex-1 p-3 space-y-1" v-else>
      <router-link
        v-for="item in panelNavItems"
        :key="item.path"
        :to="item.path"
        class="flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm transition-colors"
        :class="route.path === item.path
          ? 'bg-avito-card text-white'
          : 'text-gray-400 hover:text-white hover:bg-gray-700/30'"
      >
        <span class="text-base">{{ item.icon }}</span>
        <span>{{ item.label }}</span>
      </router-link>
    </nav>

    <!-- Footer -->
    <div class="p-4 border-t border-gray-700/50">
      <button
        v-if="tenant.isAuthenticated"
        @click="handleLogout"
        class="w-full flex items-center gap-2 px-3 py-2 rounded-lg text-sm text-gray-400 hover:text-red-400 hover:bg-gray-700/30 transition-colors"
      >
        <span>🚪</span>
        <span>Выйти</span>
      </button>
      <div v-else class="flex items-center gap-2">
        <router-link to="/login" class="text-xs text-blue-400 hover:text-blue-300">Войти</router-link>
        <span class="text-gray-600">|</span>
        <p class="text-xs text-gray-500">v0.1.0</p>
      </div>
    </div>
  </aside>
</template>

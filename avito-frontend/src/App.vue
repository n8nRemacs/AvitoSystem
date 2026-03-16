<script setup>
import { computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { useTenantStore } from './stores/tenant'
import AppSidebar from './components/layout/AppSidebar.vue'
import AppHeader from './components/layout/AppHeader.vue'

const route = useRoute()
const tenant = useTenantStore()

onMounted(() => {
  tenant.init()
})

// Guest pages (login, register, verify) use full-page layout without sidebar
const isGuestPage = computed(() => route.meta.guest === true)
</script>

<template>
  <!-- Guest layout: full-screen, no sidebar -->
  <div v-if="isGuestPage">
    <router-view />
  </div>

  <!-- Authenticated layout: sidebar + header -->
  <div v-else class="flex h-screen overflow-hidden">
    <AppSidebar />
    <div class="flex flex-col flex-1 overflow-hidden">
      <AppHeader />
      <main class="flex-1 overflow-y-auto p-6 bg-avito-dark">
        <router-view />
      </main>
    </div>
  </div>
</template>

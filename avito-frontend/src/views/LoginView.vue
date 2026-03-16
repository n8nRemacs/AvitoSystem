<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useTenantStore } from '../stores/tenant'

const router = useRouter()
const tenant = useTenantStore()

const phone = ref('+7')
const otpChannel = ref('console')

const channels = [
  { value: 'console', label: 'Console (dev)' },
  { value: 'sms', label: 'SMS' },
  { value: 'telegram', label: 'Telegram' },
  { value: 'whatsapp', label: 'WhatsApp' },
]

async function handleLogin() {
  try {
    await tenant.login(phone.value, otpChannel.value)
    router.push('/verify')
  } catch {
    // error is set in store
  }
}
</script>

<template>
  <div class="min-h-screen bg-avito-dark flex items-center justify-center p-4">
    <div class="w-full max-w-md">
      <!-- Logo -->
      <div class="text-center mb-8">
        <h1 class="text-3xl font-bold text-white">Avito System</h1>
        <p class="text-gray-400 mt-2">Войдите в личный кабинет</p>
      </div>

      <!-- Card -->
      <div class="bg-avito-sidebar rounded-xl p-8 border border-gray-700/50">
        <h2 class="text-xl font-semibold text-white mb-6">Вход</h2>

        <!-- Error -->
        <div v-if="tenant.error" class="mb-4 p-3 bg-red-500/10 border border-red-500/30 rounded-lg">
          <p class="text-sm text-red-400">{{ tenant.error }}</p>
        </div>

        <form @submit.prevent="handleLogin" class="space-y-4">
          <!-- Phone -->
          <div>
            <label class="block text-sm text-gray-400 mb-1.5">Телефон</label>
            <input
              v-model="phone"
              type="tel"
              placeholder="+79991234567"
              required
              class="w-full px-4 py-3 bg-avito-dark border border-gray-600 rounded-lg text-white text-sm focus:outline-none focus:border-blue-500 transition-colors"
            />
          </div>

          <!-- OTP Channel -->
          <div>
            <label class="block text-sm text-gray-400 mb-1.5">Получить код через</label>
            <select
              v-model="otpChannel"
              class="w-full px-4 py-3 bg-avito-dark border border-gray-600 rounded-lg text-white text-sm focus:outline-none focus:border-blue-500 transition-colors"
            >
              <option v-for="ch in channels" :key="ch.value" :value="ch.value">{{ ch.label }}</option>
            </select>
          </div>

          <!-- Submit -->
          <button
            type="submit"
            :disabled="tenant.loading"
            class="w-full py-3 bg-blue-600 hover:bg-blue-500 disabled:bg-blue-600/50 disabled:cursor-not-allowed rounded-lg text-white text-sm font-medium transition-colors"
          >
            <span v-if="tenant.loading">Отправка...</span>
            <span v-else>Получить код</span>
          </button>
        </form>

        <!-- Register link -->
        <div class="mt-6 text-center">
          <p class="text-sm text-gray-400">
            Нет аккаунта?
            <router-link to="/register" class="text-blue-400 hover:text-blue-300 transition-colors">Зарегистрироваться</router-link>
          </p>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { useTenantStore } from '../stores/tenant'

const router = useRouter()
const tenant = useTenantStore()

const code = ref('')
const countdown = ref(0)
let timer = null

const purposeLabel = computed(() => {
  switch (tenant.otpPurpose) {
    case 'register': return 'Подтверждение регистрации'
    case 'login': return 'Подтверждение входа'
    default: return 'Подтверждение'
  }
})

const channelLabel = computed(() => {
  switch (tenant.otpChannel) {
    case 'console': return 'консоль сервера (dev)'
    case 'sms': return 'SMS'
    case 'telegram': return 'Telegram'
    case 'whatsapp': return 'WhatsApp'
    case 'email': return 'email'
    default: return tenant.otpChannel
  }
})

onMounted(() => {
  // Redirect if no OTP flow in progress
  if (!tenant.otpPhone) {
    router.push('/login')
    return
  }
  countdown.value = tenant.otpExpiresIn
  timer = setInterval(() => {
    if (countdown.value > 0) countdown.value--
  }, 1000)
})

onUnmounted(() => {
  if (timer) clearInterval(timer)
})

const countdownFormatted = computed(() => {
  const m = Math.floor(countdown.value / 60)
  const s = countdown.value % 60
  return `${m}:${s.toString().padStart(2, '0')}`
})

async function handleVerify() {
  try {
    await tenant.verifyOtp(code.value)
    router.push('/dashboard')
  } catch {
    // error is set in store
  }
}

function goBack() {
  tenant.clearError()
  if (tenant.otpPurpose === 'register') {
    router.push('/register')
  } else {
    router.push('/login')
  }
}
</script>

<template>
  <div class="min-h-screen bg-avito-dark flex items-center justify-center p-4">
    <div class="w-full max-w-md">
      <!-- Logo -->
      <div class="text-center mb-8">
        <h1 class="text-3xl font-bold text-white">Avito System</h1>
        <p class="text-gray-400 mt-2">{{ purposeLabel }}</p>
      </div>

      <!-- Card -->
      <div class="bg-avito-sidebar rounded-xl p-8 border border-gray-700/50">
        <!-- Info -->
        <div class="mb-6">
          <p class="text-sm text-gray-300">
            Код отправлен на <span class="text-white font-medium">{{ tenant.otpPhone }}</span>
          </p>
          <p class="text-xs text-gray-500 mt-1">
            Канал: {{ channelLabel }}
          </p>
        </div>

        <!-- Error -->
        <div v-if="tenant.error" class="mb-4 p-3 bg-red-500/10 border border-red-500/30 rounded-lg">
          <p class="text-sm text-red-400">{{ tenant.error }}</p>
        </div>

        <form @submit.prevent="handleVerify" class="space-y-4">
          <!-- Code input -->
          <div>
            <label class="block text-sm text-gray-400 mb-1.5">Код подтверждения</label>
            <input
              v-model="code"
              type="text"
              inputmode="numeric"
              autocomplete="one-time-code"
              placeholder="000000"
              maxlength="8"
              required
              class="w-full px-4 py-4 bg-avito-dark border border-gray-600 rounded-lg text-white text-center text-2xl tracking-[0.5em] font-mono focus:outline-none focus:border-blue-500 transition-colors"
            />
          </div>

          <!-- Countdown -->
          <div class="text-center">
            <p v-if="countdown > 0" class="text-sm text-gray-400">
              Код действителен ещё <span class="text-white font-medium">{{ countdownFormatted }}</span>
            </p>
            <p v-else class="text-sm text-red-400">Код истёк. Запросите новый.</p>
          </div>

          <!-- Submit -->
          <button
            type="submit"
            :disabled="tenant.loading || code.length < 4"
            class="w-full py-3 bg-blue-600 hover:bg-blue-500 disabled:bg-blue-600/50 disabled:cursor-not-allowed rounded-lg text-white text-sm font-medium transition-colors"
          >
            <span v-if="tenant.loading">Проверка...</span>
            <span v-else>Подтвердить</span>
          </button>
        </form>

        <!-- Back -->
        <div class="mt-6 text-center">
          <button @click="goBack" class="text-sm text-gray-400 hover:text-white transition-colors">
            Назад
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

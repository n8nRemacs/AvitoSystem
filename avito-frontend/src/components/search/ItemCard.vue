<script setup>
defineProps({
  item: { type: Object, required: true },
})
</script>

<template>
  <div class="bg-avito-sidebar rounded-xl border border-gray-700/50 overflow-hidden cursor-pointer hover:border-blue-500/50 transition-colors">
    <!-- Image -->
    <div class="h-40 bg-avito-dark flex items-center justify-center overflow-hidden">
      <img
        v-if="item.images?.length"
        :src="item.images[0].url"
        :alt="item.title"
        class="w-full h-full object-cover"
        loading="lazy"
      />
      <span v-else class="text-gray-600 text-sm">No image</span>
    </div>

    <!-- Info -->
    <div class="p-3">
      <h4 class="text-sm font-medium text-white truncate">{{ item.title }}</h4>
      <p class="text-lg font-bold text-blue-400 mt-1">
        {{ item.price_text || (item.price ? item.price.toLocaleString('ru-RU') + ' ₽' : 'Price on request') }}
      </p>
      <p class="text-xs text-gray-500 mt-1 truncate">{{ item.city || item.address || '' }}</p>
    </div>
  </div>
</template>

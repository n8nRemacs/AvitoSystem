<script setup>
import { useSearchStore } from '../../stores/search'

const searchStore = useSearchStore()

function close() {
  searchStore.selectedItem = null
}
</script>

<template>
  <teleport to="body">
    <div class="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4" @click.self="close">
      <div class="bg-avito-sidebar rounded-xl border border-gray-700/50 w-full max-w-2xl max-h-[90vh] overflow-y-auto">
        <!-- Header -->
        <div class="flex items-center justify-between p-4 border-b border-gray-700/50">
          <h3 class="text-lg font-semibold text-white">{{ searchStore.selectedItem.title }}</h3>
          <button @click="close" class="text-gray-400 hover:text-white text-lg">&times;</button>
        </div>

        <!-- Images -->
        <div v-if="searchStore.selectedItem.images?.length" class="flex gap-2 p-4 overflow-x-auto">
          <img
            v-for="(img, i) in searchStore.selectedItem.images"
            :key="i"
            :src="img.url"
            class="h-48 rounded-lg object-cover"
            loading="lazy"
          />
        </div>

        <!-- Details -->
        <div class="p-4 space-y-3">
          <p class="text-2xl font-bold text-blue-400">
            {{ searchStore.selectedItem.price_text || (searchStore.selectedItem.price?.toLocaleString('ru-RU') + ' ₽') }}
          </p>

          <div v-if="searchStore.selectedItem.description" class="text-sm text-gray-300 whitespace-pre-wrap">
            {{ searchStore.selectedItem.description }}
          </div>

          <div class="grid grid-cols-2 gap-2 text-sm">
            <div v-if="searchStore.selectedItem.city">
              <span class="text-gray-500">City: </span>
              <span class="text-gray-300">{{ searchStore.selectedItem.city }}</span>
            </div>
            <div v-if="searchStore.selectedItem.address">
              <span class="text-gray-500">Address: </span>
              <span class="text-gray-300">{{ searchStore.selectedItem.address }}</span>
            </div>
            <div v-if="searchStore.selectedItem.category">
              <span class="text-gray-500">Category: </span>
              <span class="text-gray-300">{{ searchStore.selectedItem.category }}</span>
            </div>
            <div v-if="searchStore.selectedItem.seller_name">
              <span class="text-gray-500">Seller: </span>
              <span class="text-gray-300">{{ searchStore.selectedItem.seller_name }}</span>
            </div>
          </div>

          <div class="flex gap-2 pt-2">
            <button
              @click="close"
              class="px-4 py-2 bg-blue-600 hover:bg-blue-500 rounded-lg text-sm text-white"
            >
              Write to seller
            </button>
          </div>
        </div>
      </div>
    </div>
  </teleport>
</template>

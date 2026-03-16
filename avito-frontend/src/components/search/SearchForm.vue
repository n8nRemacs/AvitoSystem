<script setup>
import { ref } from 'vue'
import { useSearchStore } from '../../stores/search'

const searchStore = useSearchStore()
const query = ref('')
const priceMin = ref(null)
const priceMax = ref(null)
const sort = ref(null)

function search() {
  if (!query.value.trim()) return
  searchStore.searchItems({
    query: query.value,
    price_min: priceMin.value || null,
    price_max: priceMax.value || null,
    sort: sort.value || null,
  })
}
</script>

<template>
  <div class="bg-avito-sidebar rounded-xl p-5 border border-gray-700/50">
    <div class="flex flex-wrap gap-3">
      <input
        v-model="query"
        @keydown.enter="search"
        type="text"
        placeholder="Search Avito..."
        class="flex-1 min-w-[200px] px-3 py-2 bg-avito-dark border border-gray-600 rounded-lg text-sm text-white focus:outline-none focus:border-blue-500"
      />
      <input
        v-model.number="priceMin"
        type="number"
        placeholder="Price from"
        class="w-32 px-3 py-2 bg-avito-dark border border-gray-600 rounded-lg text-sm text-white focus:outline-none focus:border-blue-500"
      />
      <input
        v-model.number="priceMax"
        type="number"
        placeholder="Price to"
        class="w-32 px-3 py-2 bg-avito-dark border border-gray-600 rounded-lg text-sm text-white focus:outline-none focus:border-blue-500"
      />
      <select
        v-model="sort"
        class="px-3 py-2 bg-avito-dark border border-gray-600 rounded-lg text-sm text-white focus:outline-none focus:border-blue-500"
      >
        <option :value="null">Sort by</option>
        <option value="date">Newest</option>
        <option value="price">Price (low)</option>
        <option value="price_desc">Price (high)</option>
      </select>
      <button
        @click="search"
        :disabled="!query.trim() || searchStore.loading"
        class="px-6 py-2 bg-blue-600 hover:bg-blue-500 disabled:opacity-50 rounded-lg text-sm text-white transition-colors"
      >
        {{ searchStore.loading ? 'Searching...' : 'Search' }}
      </button>
    </div>
  </div>
</template>

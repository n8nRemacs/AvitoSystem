<script setup>
import { useSearchStore } from '../stores/search'
import SearchForm from '../components/search/SearchForm.vue'
import ItemCard from '../components/search/ItemCard.vue'
import ItemDetail from '../components/search/ItemDetail.vue'

const searchStore = useSearchStore()
</script>

<template>
  <div class="space-y-6">
    <h2 class="text-2xl font-bold">Search</h2>

    <SearchForm />

    <!-- Results grid -->
    <div v-if="searchStore.items.length > 0">
      <p class="text-sm text-gray-400 mb-3">
        Found: {{ searchStore.totalCount || searchStore.items.length }} items
      </p>
      <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
        <ItemCard
          v-for="item in searchStore.items"
          :key="item.id"
          :item="item"
          @click="searchStore.getItemDetails(item.id)"
        />
      </div>
      <div v-if="searchStore.hasMore" class="mt-4 text-center">
        <button
          @click="searchStore.loadMore()"
          :disabled="searchStore.loading"
          class="px-6 py-2 bg-avito-card hover:bg-blue-600/30 rounded-lg text-sm text-gray-300 transition-colors"
        >
          {{ searchStore.loading ? 'Loading...' : 'Load more' }}
        </button>
      </div>
    </div>

    <div v-else-if="searchStore.searchParams.query && !searchStore.loading" class="text-gray-500 text-sm text-center py-8">
      No results found
    </div>

    <!-- Item detail modal -->
    <ItemDetail v-if="searchStore.selectedItem" />
  </div>
</template>

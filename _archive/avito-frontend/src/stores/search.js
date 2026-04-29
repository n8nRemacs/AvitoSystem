import { defineStore } from 'pinia'
import api from '../api'

export const useSearchStore = defineStore('search', {
  state: () => ({
    items: [],
    totalCount: null,
    searchParams: {
      query: '',
      price_min: null,
      price_max: null,
      location_id: null,
      category_id: null,
      sort: null,
      page: 1,
    },
    selectedItem: null,
    hasMore: false,
    loading: false,
  }),

  actions: {
    async searchItems(params = {}) {
      this.loading = true
      Object.assign(this.searchParams, params, { page: 1 })
      try {
        const { data } = await api.get('/search/items', { params: this._cleanParams() })
        this.items = data.items
        this.totalCount = data.total
        this.hasMore = data.has_more
        this.searchParams.page = data.page
      } catch (e) {
        console.error('search error:', e)
      }
      this.loading = false
    },

    async loadMore() {
      if (!this.hasMore || this.loading) return
      this.loading = true
      this.searchParams.page++
      try {
        const { data } = await api.get('/search/items', { params: this._cleanParams() })
        this.items.push(...data.items)
        this.hasMore = data.has_more
      } catch (e) {
        this.searchParams.page--
      }
      this.loading = false
    },

    async getItemDetails(itemId) {
      try {
        const { data } = await api.get(`/search/items/${itemId}`)
        this.selectedItem = data
      } catch (e) {
        console.error('item detail error:', e)
      }
    },

    _cleanParams() {
      const p = { ...this.searchParams }
      Object.keys(p).forEach((k) => {
        if (p[k] === null || p[k] === '' || p[k] === undefined) delete p[k]
      })
      return p
    },
  },
})

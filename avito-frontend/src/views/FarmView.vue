<script setup>
import { onMounted } from 'vue'
import { useFarmStore } from '../stores/farm'
import DeviceList from '../components/farm/DeviceList.vue'
import BindingTable from '../components/farm/BindingTable.vue'

const farmStore = useFarmStore()

onMounted(() => {
  farmStore.fetchAll()
})
</script>

<template>
  <div class="space-y-6">
    <h2 class="text-2xl font-bold">Token Farm</h2>

    <DeviceList />
    <BindingTable />
  </div>
</template>

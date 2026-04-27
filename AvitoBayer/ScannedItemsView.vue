<template>
  <div>
    <n-space vertical :size="24">
      <!-- Stats -->
      <n-grid :cols="6" :x-gap="12">
        <n-gi><n-statistic label="Всего" :value="items.length" /></n-gi>
        <n-gi><n-statistic label="Подходит" :value="items.filter(i => i.llm_verdict === 'ok').length">
          <template #prefix><span style="color:#18a058;">&bull;</span></template>
        </n-statistic></n-gi>
        <n-gi><n-statistic label="Частично" :value="items.filter(i => i.llm_verdict === 'partial').length">
          <template #prefix><span style="color:#f0a020;">&bull;</span></template>
        </n-statistic></n-gi>
        <n-gi><n-statistic label="Риск" :value="items.filter(i => i.llm_verdict === 'risk').length">
          <template #prefix><span style="color:#d03050;">&bull;</span></template>
        </n-statistic></n-gi>
        <n-gi><n-statistic label="Зарезервировано" :value="items.filter(i => i.is_reserved).length" /></n-gi>
        <n-gi><n-statistic label="Отправлено в TG" :value="items.filter(i => i.status === 'sent_to_tg').length" /></n-gi>
      </n-grid>

      <!-- Filters -->
      <n-card size="small">
        <n-space>
          <n-select v-model:value="filters.verdict" placeholder="Вердикт" clearable :options="verdictOptions" style="width: 160px;" @update:value="loadItems" />
          <n-select v-model:value="filters.status" placeholder="Статус" clearable :options="statusOptions" style="width: 160px;" @update:value="loadItems" />
          <n-select v-model:value="filters.search_id" placeholder="Поиск" clearable :options="searchOptions" style="width: 220px;" @update:value="loadItems" />
          <n-input v-model:value="filters.model" placeholder="Модель..." clearable style="width: 160px;" @update:value="loadItems" />
          <n-select v-model:value="filters.reserved" placeholder="Резерв" clearable :options="reservedOptions" style="width: 140px;" @update:value="loadItems" />
          <n-date-picker v-model:value="filters.dateRange" type="daterange" clearable style="width: 260px;" @update:value="loadItems" />
          <n-button @click="loadItems" :loading="loading">Обновить</n-button>
        </n-space>
      </n-card>

      <!-- Table -->
      <n-data-table
        :columns="columns"
        :data="items"
        :loading="loading"
        :row-key="(r) => r.id"
        :row-class-name="rowClass"
        size="small"
        :pagination="{ pageSize: 30 }"
        :scroll-x="1400"
      />
    </n-space>

    <!-- Detail Modal -->
    <n-modal v-model:show="showDetail" preset="card" :title="detailItem?.title ?? ''" style="width: 800px; max-height: 85vh;">
      <n-scrollbar style="max-height: 70vh;" v-if="detailItem">
        <!-- Images -->
        <n-space v-if="detailItem.images?.length" style="margin-bottom: 16px;">
          <n-image
            v-for="(img, idx) in detailItem.images.slice(0, 6)"
            :key="idx"
            :src="img"
            width="120"
            height="120"
            object-fit="cover"
            style="border-radius: 8px;"
            lazy
          />
        </n-space>

        <!-- Info grid -->
        <n-descriptions bordered :column="2" size="small" style="margin-bottom: 16px;">
          <n-descriptions-item label="Цена">{{ detailItem.price?.toLocaleString('ru-RU') }} &#8381;</n-descriptions-item>
          <n-descriptions-item label="Модель">{{ detailItem.model || '\u2014' }}</n-descriptions-item>
          <n-descriptions-item label="Город">{{ detailItem.location || '\u2014' }}</n-descriptions-item>
          <n-descriptions-item label="АКБ">{{ detailItem.battery_pct ? detailItem.battery_pct + '%' : '\u2014' }}</n-descriptions-item>
          <n-descriptions-item label="Память">{{ detailItem.storage_gb ? detailItem.storage_gb + ' GB' : '\u2014' }}</n-descriptions-item>
          <n-descriptions-item label="Цвет">{{ detailItem.color || '\u2014' }}</n-descriptions-item>
          <n-descriptions-item label="Резерв">
            <n-tag :type="detailItem.is_reserved ? 'error' : 'success'" size="small">
              {{ detailItem.is_reserved ? 'Зарезервирован' : 'Свободен' }}
            </n-tag>
          </n-descriptions-item>
          <n-descriptions-item label="Опубликовано">{{ fmtDate(detailItem.published_at) }}</n-descriptions-item>
          <n-descriptions-item label="Продавец">
            {{ detailItem.seller_name || '\u2014' }}
            <span v-if="detailItem.seller_rating" style="color:#f0a020;"> &#9733;{{ detailItem.seller_rating }}</span>
            <span v-if="detailItem.seller_reviews" style="color:#888;"> ({{ detailItem.seller_reviews }} отзывов)</span>
          </n-descriptions-item>
          <n-descriptions-item label="На Avito с">{{ detailItem.seller_reg_year || '\u2014' }}</n-descriptions-item>
        </n-descriptions>

        <!-- LLM Analysis -->
        <n-card title="LLM Анализ" size="small" style="margin-bottom: 16px;">
          <n-space vertical :size="8">
            <n-space>
              <n-tag :type="verdictType(detailItem.llm_verdict)" size="small">{{ verdictLabel(detailItem.llm_verdict) }}</n-tag>
              <span v-if="detailItem.llm_score">Score: <b>{{ detailItem.llm_score }}</b>/10</span>
            </n-space>
            <p v-if="detailItem.llm_summary" style="margin: 0;">{{ detailItem.llm_summary }}</p>

            <n-space v-if="detailItem.llm_green_flags?.length">
              <n-tag v-for="f in detailItem.llm_green_flags" :key="f" type="success" size="small">&#10004; {{ f }}</n-tag>
            </n-space>
            <n-space v-if="detailItem.llm_red_flags?.length">
              <n-tag v-for="f in detailItem.llm_red_flags" :key="f" type="error" size="small">&#10008; {{ f }}</n-tag>
            </n-space>
            <n-space v-if="detailItem.llm_missing_info?.length">
              <n-tag v-for="f in detailItem.llm_missing_info" :key="f" type="warning" size="small">? {{ f }}</n-tag>
            </n-space>
          </n-space>
        </n-card>

        <!-- Description -->
        <n-card title="Описание" size="small" v-if="detailItem.description">
          <pre style="white-space: pre-wrap; font-size: 12px; margin: 0;">{{ detailItem.description }}</pre>
        </n-card>
      </n-scrollbar>

      <template #footer>
        <n-space justify="end">
          <n-button v-if="detailItem?.url" tag="a" :href="detailItem.url" target="_blank">Открыть на Avito</n-button>
          <n-button type="primary" @click="markViewed(detailItem)" v-if="detailItem?.status === 'new'">Просмотрено</n-button>
        </n-space>
      </template>
    </n-modal>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, h, computed } from 'vue'
import {
  NSpace, NGrid, NGi, NStatistic, NDataTable, NButton, NCard,
  NModal, NTag, NSelect, NInput, NDatePicker, NImage, NScrollbar,
  NDescriptions, NDescriptionsItem, NSwitch,
  useMessage,
} from 'naive-ui'
import type { DataTableColumns } from 'naive-ui'
import axios from 'axios'

const SB_URL = 'http://213.108.170.194:8000/rest/v1'
const SB_KEY = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJyb2xlIjoic2VydmljZV9yb2xlIiwiaXNzIjoic3VwYWJhc2UiLCJpYXQiOjE3NzEyNjMzMzcsImV4cCI6MjA4NjYyMzMzN30.ZSYI-yiRN3bZ8rygtsre6HhLdaKtIusCC7AfDjYoxN8'

const sb = axios.create({
  baseURL: SB_URL,
  headers: { apikey: SB_KEY, Authorization: `Bearer ${SB_KEY}`, 'Content-Type': 'application/json', Prefer: 'return=representation' },
})

const msg = useMessage()
const items = ref<any[]>([])
const searches = ref<any[]>([])
const loading = ref(false)
const showDetail = ref(false)
const detailItem = ref<any>(null)

const filters = ref<{
  verdict: string | null
  status: string | null
  search_id: string | null
  model: string | null
  reserved: string | null
  dateRange: [number, number] | null
}>({
  verdict: null, status: null, search_id: null, model: null, reserved: null, dateRange: null,
})

const verdictOptions = [
  { label: '\u2705 Подходит', value: 'ok' },
  { label: '\u26A0 Частично', value: 'partial' },
  { label: '\u274C Риск', value: 'risk' },
  { label: '\u23ED Пропустить', value: 'skip' },
]
const statusOptions = [
  { label: 'Новый', value: 'new' },
  { label: 'В TG', value: 'sent_to_tg' },
  { label: 'Просмотрен', value: 'viewed' },
  { label: 'Связались', value: 'contacted' },
  { label: 'Отклонён', value: 'rejected' },
  { label: 'В лидах', value: 'in_leads' },
]
const reservedOptions = [
  { label: 'Свободен', value: 'false' },
  { label: 'Зарезервирован', value: 'true' },
]

const searchOptions = computed(() =>
  searches.value.map(s => ({ label: s.name, value: s.id }))
)

function fmtDate(d: string | null) {
  if (!d) return '\u2014'
  return new Date(d).toLocaleString('ru-RU', { day: '2-digit', month: '2-digit', year: '2-digit', hour: '2-digit', minute: '2-digit' })
}

function verdictType(v: string | null): string {
  const m: Record<string, string> = { ok: 'success', partial: 'warning', risk: 'error', skip: 'default' }
  return m[v ?? ''] ?? 'default'
}

function verdictLabel(v: string | null): string {
  const m: Record<string, string> = { ok: 'Подходит', partial: 'Частично', risk: 'Риск', skip: 'Пропуск' }
  return m[v ?? ''] ?? v ?? '\u2014'
}

function rowClass(row: any) {
  if (row.is_reserved) return 'row-reserved'
  if (row.llm_verdict === 'ok') return 'row-ok'
  if (row.llm_verdict === 'risk') return 'row-risk'
  return ''
}

const columns: DataTableColumns<any> = [
  {
    title: '', key: 'thumb', width: 50,
    render: (row) => row.images?.[0]
      ? h('img', { src: row.images[0], style: 'width:40px;height:40px;object-fit:cover;border-radius:4px;cursor:pointer;', onClick: () => openDetail(row) })
      : '',
  },
  {
    title: 'Название', key: 'title', ellipsis: { tooltip: true },
    render: (row) => h(NButton, { text: true, onClick: () => openDetail(row) }, () => row.title),
  },
  {
    title: 'Цена', key: 'price', width: 100, sorter: (a, b) => (a.price ?? 0) - (b.price ?? 0),
    render: (row) => row.price ? row.price.toLocaleString('ru-RU') + ' \u20BD' : '\u2014',
  },
  { title: 'Модель', key: 'model', width: 120, ellipsis: { tooltip: true } },
  {
    title: 'Вердикт', key: 'llm_verdict', width: 100,
    render: (row) => row.llm_verdict ? h(NTag, { type: verdictType(row.llm_verdict) as any, size: 'small' }, () => verdictLabel(row.llm_verdict)) : '\u2014',
    sorter: (a, b) => { const o: Record<string,number> = {ok:0,partial:1,risk:2,skip:3}; return (o[a.llm_verdict]??9) - (o[b.llm_verdict]??9) },
  },
  {
    title: 'Score', key: 'llm_score', width: 70, sorter: (a, b) => (a.llm_score ?? 0) - (b.llm_score ?? 0),
    render: (row) => row.llm_score != null ? String(row.llm_score) : '\u2014',
  },
  {
    title: 'Резерв', key: 'is_reserved', width: 80,
    render: (row) => row.is_reserved ? h(NTag, { type: 'error', size: 'small' }, () => 'Да') : '',
  },
  { title: 'Город', key: 'location', width: 100, ellipsis: { tooltip: true } },
  {
    title: 'Опубликовано', key: 'published_at', width: 110, sorter: (a, b) => new Date(a.published_at ?? 0).getTime() - new Date(b.published_at ?? 0).getTime(),
    render: (row) => fmtDate(row.published_at),
  },
  {
    title: 'Статус', key: 'status', width: 90,
    render: (row) => {
      const m: Record<string,{l:string;t:string}> = {
        new:{l:'Новый',t:'info'}, sent_to_tg:{l:'В TG',t:'success'}, viewed:{l:'Просм.',t:'default'},
        contacted:{l:'Связ.',t:'warning'}, rejected:{l:'Откл.',t:'error'}, in_leads:{l:'В лидах',t:'success'},
      }
      const i = m[row.status]; return i ? h(NTag, { type: i.t as any, size: 'small' }, () => i.l) : row.status
    },
  },
  {
    title: 'Скан', key: 'scanned_at', width: 110,
    render: (row) => fmtDate(row.scanned_at),
  },
]

function openDetail(row: any) {
  detailItem.value = row
  showDetail.value = true
}

async function markViewed(item: any) {
  await sb.patch('/scanned_items', { status: 'viewed', viewed_at: new Date().toISOString() }, { params: { id: `eq.${item.id}` } })
  item.status = 'viewed'
  item.viewed_at = new Date().toISOString()
  msg.success('Помечено как просмотренное')
}

async function loadItems() {
  loading.value = true
  try {
    const params: Record<string, string> = { select: '*', order: 'scanned_at.desc', limit: '200' }
    if (filters.value.verdict) params.llm_verdict = `eq.${filters.value.verdict}`
    if (filters.value.status) params.status = `eq.${filters.value.status}`
    if (filters.value.search_id) params.search_id = `eq.${filters.value.search_id}`
    if (filters.value.model) params.model = `ilike.*${filters.value.model}*`
    if (filters.value.reserved) params.is_reserved = `eq.${filters.value.reserved}`
    if (filters.value.dateRange) {
      const [from, to] = filters.value.dateRange
      params.published_at = `gte.${new Date(from).toISOString()}`
      params['published_at'] = `gte.${new Date(from).toISOString()}`
    }
    const { data } = await sb.get('/scanned_items', { params })
    items.value = data
  } finally { loading.value = false }
}

async function loadSearches() {
  const { data } = await sb.get('/saved_searches', { params: { select: 'id,name', order: 'created_at.desc' } })
  searches.value = data
}

onMounted(() => { loadItems(); loadSearches() })
</script>

<style>
.row-reserved td { opacity: 0.5; }
.row-ok td:first-child { border-left: 3px solid #18a058 !important; }
.row-risk td:first-child { border-left: 3px solid #d03050 !important; }
</style>

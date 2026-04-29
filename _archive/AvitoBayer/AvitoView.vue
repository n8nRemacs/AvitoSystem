<template>
  <div>
    <n-space vertical :size="24">
      <n-grid :cols="5" :x-gap="16">
        <n-gi><n-statistic label="Всего поисков" :value="searches.length" /></n-gi>
        <n-gi><n-statistic label="Активных" :value="searches.filter(s => s.is_active).length" /></n-gi>
        <n-gi><n-statistic label="Покупка" :value="searches.filter(s => s.search_type === 'buy').length" /></n-gi>
        <n-gi><n-statistic label="Конкуренты" :value="searches.filter(s => s.search_type === 'competitors').length" /></n-gi>
        <n-gi><n-statistic label="Мониторинг цен" :value="searches.filter(s => s.search_type === 'price_monitor').length" /></n-gi>
      </n-grid>

      <n-tabs type="line" animated>
        <n-tab-pane name="searches" tab="Поисковые запросы">
          <n-space style="margin-bottom: 16px;">
            <n-button type="primary" @click="showAdd = true">+ Добавить поиск</n-button>
          </n-space>
          <n-data-table :columns="searchColumns" :data="searches" :loading="loading" :row-key="(r) => r.id" size="small" />
        </n-tab-pane>

        <n-tab-pane name="rules" tab="Правила обработки">
          <n-data-table :columns="ruleColumns" :data="rules" :row-key="(r) => r.id" size="small" />
        </n-tab-pane>
      </n-tabs>
    </n-space>

    <!-- Add Search Modal -->
    <n-modal v-model:show="showAdd" preset="card" title="Добавить поисковый запрос" style="width: 600px;">
      <n-form label-placement="top">
        <n-form-item label="Название"><n-input v-model:value="addForm.name" placeholder="iPhone 12 Pro 9-13к" /></n-form-item>
        <n-form-item label="URL с Avito"><n-input v-model:value="addForm.avito_url" placeholder="https://www.avito.ru/all/telefony/..." /></n-form-item>
        <n-form-item label="Тип"><n-select v-model:value="addForm.search_type" :options="typeOptions" /></n-form-item>
        <n-form-item label="Описание"><n-input v-model:value="addForm.description" type="textarea" :rows="2" /></n-form-item>
      </n-form>
      <template #footer>
        <n-space justify="end">
          <n-button @click="showAdd = false">Отмена</n-button>
          <n-button type="primary" :loading="saving" @click="doSaveSearch">Сохранить</n-button>
        </n-space>
      </template>
    </n-modal>

    <!-- Edit Rule Modal -->
    <n-modal v-model:show="showEditRule" preset="card" :title="'Правило: ' + (editingRule?.name ?? '')" style="width: 720px;">
      <n-form v-if="editingRule" label-placement="top">
        <n-form-item label="Название"><n-input v-model:value="editingRule.name" /></n-form-item>
        <n-grid :cols="3" :x-gap="12">
          <n-gi><n-form-item label="Порог скоринга"><n-input-number v-model:value="editingRule.score_threshold" :min="0" :max="10" :step="0.5" style="width:100%;" /></n-form-item></n-gi>
          <n-gi><n-form-item label="Интервал сканирования (мин)"><n-input-number v-model:value="editingRule.check_interval_minutes" :min="1" :max="60" style="width:100%;" /></n-form-item></n-gi>
          <n-gi><n-form-item label="Макс лидов за проход"><n-input-number v-model:value="editingRule.max_leads_per_run" :min="0" style="width:100%;" /></n-form-item></n-gi>
        </n-grid>
        <n-grid :cols="3" :x-gap="12">
          <n-gi><n-form-item label="Алерт: новые"><n-switch v-model:value="editingRule.alert_on_new" /></n-form-item></n-gi>
          <n-gi><n-form-item label="Алерт: цена"><n-switch v-model:value="editingRule.alert_on_price_change" /></n-form-item></n-gi>
          <n-gi><n-form-item label="Падение цены (%)"><n-input-number v-model:value="editingRule.alert_on_price_drop_pct" :min="1" :max="100" style="width:100%;" /></n-form-item></n-gi>
        </n-grid>
        <n-grid :cols="2" :x-gap="12">
          <n-gi>
            <n-form-item label="Зелёные флаги (хорошие признаки)">
              <n-dynamic-tags v-model:value="editingRule.green_flags" type="success" />
            </n-form-item>
          </n-gi>
          <n-gi>
            <n-form-item label="Красные флаги (плохие признаки)">
              <n-dynamic-tags v-model:value="editingRule.red_flags" type="error" />
            </n-form-item>
          </n-gi>
        </n-grid>
        <n-form-item label="LLM промпт (анализ описания объявления)">
          <n-input v-model:value="editingRule.llm_prompt" type="textarea" :rows="12" placeholder="Промпт для анализа описания..." style="font-family: monospace; font-size: 12px;" />
        </n-form-item>
      </n-form>
      <template #footer>
        <n-space justify="end">
          <n-button @click="showEditRule = false">Отмена</n-button>
          <n-button type="primary" :loading="savingRule" @click="doSaveRule">Сохранить</n-button>
        </n-space>
      </template>
    </n-modal>

    <!-- History Modal -->
    <n-modal v-model:show="showHistory" preset="card" :title="'История: ' + (historySearch?.name ?? '')" style="width: 700px;">
      <n-data-table :columns="historyColumns" :data="runs" :loading="runsLoading" :row-key="(r) => r.id" size="small" />
    </n-modal>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, h } from 'vue'
import {
  NSpace, NGrid, NGi, NStatistic, NTabs, NTabPane, NDataTable, NButton,
  NModal, NForm, NFormItem, NInput, NSelect, NInputNumber, NSwitch, NTag,
  NDynamicTags, useMessage,
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
const searches = ref<any[]>([])
const rules = ref<any[]>([])
const runs = ref<any[]>([])
const loading = ref(false)
const runsLoading = ref(false)
const saving = ref(false)
const savingRule = ref(false)
const showAdd = ref(false)
const showEditRule = ref(false)
const showHistory = ref(false)
const editingRule = ref<any>(null)
const historySearch = ref<any>(null)
const addForm = ref({ name: '', avito_url: '', search_type: 'buy', description: '' })

const typeOptions = [
  { label: 'Покупка', value: 'buy' },
  { label: 'Конкуренты', value: 'competitors' },
  { label: 'Мониторинг цен', value: 'price_monitor' },
]

const typeMap: Record<string, { label: string; type: string }> = {
  buy: { label: 'Покупка', type: 'success' },
  competitors: { label: 'Конкуренты', type: 'info' },
  price_monitor: { label: 'Мониторинг', type: 'warning' },
}

function fmtDate(d: string | null) {
  if (!d) return '\u2014'
  return new Date(d).toLocaleString('ru-RU', { day: '2-digit', month: '2-digit', year: '2-digit', hour: '2-digit', minute: '2-digit' })
}

function fmtPrice(v: number | null) {
  if (!v) return '\u2014'
  return Math.round(v).toLocaleString('ru-RU') + ' \u20BD'
}

const searchColumns: DataTableColumns<any> = [
  {
    title: '', key: 'is_active', width: 50,
    render: (row) => h(NSwitch, {
      value: row.is_active, size: 'small',
      onUpdateValue: async (val: boolean) => { await sb.patch('/saved_searches', { is_active: val }, { params: { id: `eq.${row.id}` } }); row.is_active = val },
    }),
  },
  { title: 'Название', key: 'name', ellipsis: { tooltip: true } },
  {
    title: 'Тип', key: 'search_type', width: 120,
    render: (row) => { const i = typeMap[row.search_type]; return i ? h(NTag, { type: i.type as any, size: 'small' }, () => i.label) : row.search_type },
  },
  {
    title: 'Правило', key: 'rule',
    render: (row) => { const r = row.search_processing_rules; return r ? h(NButton, { text: true, size: 'small', onClick: () => { editingRule.value = { ...r }; showEditRule.value = true } }, () => r.name) : '\u2014' },
  },
  {
    title: 'URL', key: 'avito_url', ellipsis: { tooltip: true }, width: 200,
    render: (row) => h('a', { href: row.avito_url, target: '_blank', style: 'color:#7fe7c4;' }, row.avito_url.replace('https://www.avito.ru/', '').substring(0, 40) + '...'),
  },
  { title: 'Запуск', key: 'last_run_at', width: 120, render: (row) => fmtDate(row.last_run_at) },
  {
    title: '', key: 'actions', width: 90,
    render: (row) => h(NSpace, { size: 4 }, () => [
      h(NButton, { size: 'tiny', secondary: true, onClick: () => loadHistory(row) }, () => '\uD83D\uDCCA'),
      h(NButton, { size: 'tiny', secondary: true, type: 'error', onClick: () => doDelete(row.id) }, () => '\u2715'),
    ]),
  },
]

const ruleColumns: DataTableColumns<any> = [
  { title: 'Название', key: 'name' },
  { title: 'Тип', key: 'search_type', width: 120, render: (row) => { const i = typeMap[row.search_type]; return i ? h(NTag, { type: i.type as any, size: 'small' }, () => i.label) : row.search_type } },
  { title: 'Score', key: 'score_threshold', width: 80 },
  { title: 'Интервал', key: 'check_interval_minutes', width: 90, render: (row) => `${row.check_interval_minutes} мин` },
  { title: 'Лидов', key: 'max_leads_per_run', width: 70 },
  {
    title: 'Флаги', key: 'flags', width: 100,
    render: (row) => h(NSpace, { size: 4 }, () => [
      row.green_flags?.length ? h(NTag, { type: 'success', size: 'small' }, () => `\u2714 ${row.green_flags.length}`) : null,
      row.red_flags?.length ? h(NTag, { type: 'error', size: 'small' }, () => `\u2718 ${row.red_flags.length}`) : null,
    ].filter(Boolean)),
  },
  {
    title: 'Промпт', key: 'llm_prompt', width: 80,
    render: (row) => row.llm_prompt ? h(NTag, { type: 'info', size: 'small' }, () => 'LLM') : '\u2014',
  },
  {
    title: 'Алерты', key: 'alerts',
    render: (row) => h(NSpace, { size: 4 }, () => [
      row.alert_on_new ? h(NTag, { type: 'success', size: 'small' }, () => 'Новые') : null,
      row.alert_on_price_change ? h(NTag, { type: 'warning', size: 'small' }, () => 'Цена') : null,
      row.alert_on_price_drop_pct ? h(NTag, { type: 'error', size: 'small' }, () => `>${row.alert_on_price_drop_pct}%`) : null,
    ].filter(Boolean)),
  },
  { title: '', width: 50, render: (row) => h(NButton, { size: 'tiny', onClick: () => { editingRule.value = { ...row }; showEditRule.value = true } }, () => '\u270E') },
]

const historyColumns: DataTableColumns<any> = [
  { title: 'Дата', key: 'run_at', render: (row) => fmtDate(row.run_at) },
  { title: 'Найдено', key: 'results_count', width: 80 },
  { title: 'Ср. цена', key: 'avg_price', render: (row) => fmtPrice(row.avg_price) },
  { title: 'Мин', key: 'min_price', render: (row) => fmtPrice(row.min_price) },
  { title: 'Макс', key: 'max_price', render: (row) => fmtPrice(row.max_price) },
  { title: 'Новых', key: 'new_items_count', width: 70 },
  { title: 'Лидов', key: 'leads_created', width: 70 },
]

async function loadSearches() {
  loading.value = true
  try { const { data } = await sb.get('/saved_searches', { params: { select: '*,search_processing_rules(*)', order: 'created_at.desc' } }); searches.value = data }
  finally { loading.value = false }
}

async function loadRules() {
  const { data } = await sb.get('/search_processing_rules', { params: { select: '*', order: 'created_at.desc' } }); rules.value = data
}

async function doSaveSearch() {
  saving.value = true
  try {
    const ruleForType = rules.value.find((r: any) => r.search_type === addForm.value.search_type)
    await sb.post('/saved_searches', { ...addForm.value, processing_rules_id: ruleForType?.id ?? null })
    msg.success('Поиск сохранён'); showAdd.value = false
    addForm.value = { name: '', avito_url: '', search_type: 'buy', description: '' }
    await loadSearches()
  } catch (e: any) { msg.error(e.message) } finally { saving.value = false }
}

async function doDelete(id: string) {
  await sb.delete('/search_runs', { params: { search_id: `eq.${id}` } })
  await sb.delete('/saved_searches', { params: { id: `eq.${id}` } })
  msg.success('Удалено'); await loadSearches()
}

async function doSaveRule() {
  savingRule.value = true
  try {
    const { id, created_at, ...updates } = editingRule.value
    updates.updated_at = new Date().toISOString()
    await sb.patch('/search_processing_rules', updates, { params: { id: `eq.${id}` } })
    msg.success('Правило обновлено'); showEditRule.value = false; await loadRules(); await loadSearches()
  } catch (e: any) { msg.error(e.message) } finally { savingRule.value = false }
}

async function loadHistory(search: any) {
  historySearch.value = search; showHistory.value = true; runsLoading.value = true
  try { const { data } = await sb.get('/search_runs', { params: { search_id: `eq.${search.id}`, select: '*', order: 'run_at.desc', limit: '30' } }); runs.value = data }
  finally { runsLoading.value = false }
}

onMounted(() => { loadSearches(); loadRules() })
</script>

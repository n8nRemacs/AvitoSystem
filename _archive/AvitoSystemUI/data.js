// Sample data — running example for all screens. Numbers verbatim from spec §3.
window.AM_DATA = {
  profile: {
    id: 'prof-abc123',
    name: 'iPhone 12 Pro Max до 13.5K',
    parsed_category: 'Телефоны / Мобильные телефоны',
    parsed_brand: 'Apple',
    parsed_model: 'iPhone 12 Pro Max',
    region_slug: 'Москва',
    avito_search_url: 'https://www.avito.ru/moskva/telefony/mobilnye_telefony/apple-ASgBAgICAUSwwQ2OWg?pmin=11000&pmax=13500',
    search_min_price: 8250,
    search_max_price: 16875,
    alert_min_price: 11000,
    alert_max_price: 13500,
    poll_interval_minutes: 5,
    last_run_at: '25.04 10:34',
    is_active: true,
  },
  otherProfiles: [
    { id: 'prof-def456', name: 'MacBook Air M2 до 75K', active: true, new24h: 2,
      median: 68500, alert: 4, working: 3,
      mix: { working: 50, screen: 20, other: 15, parts: 15 },
      alert_min: 60000, alert_max: 75000, search_min: 45000, search_max: 93750 },
    { id: 'prof-ghi789', name: 'AirPods Pro 2 до 12K', active: false, new24h: 0,
      median: 10500, alert: 0, working: 0,
      mix: { working: 60, screen: 0, other: 10, parts: 30 },
      alert_min: 8000, alert_max: 12000, search_min: 6000, search_max: 15000 },
    { id: 'prof-jkl012', name: 'Apple Watch Series 9 до 25K', active: true, new24h: 5,
      median: 22300, alert: 6, working: 4,
      mix: { working: 55, screen: 15, other: 10, parts: 20 },
      alert_min: 18000, alert_max: 25000, search_min: 13500, search_max: 31250 },
  ],

  listings: [
    { id: 4823951, title: 'iPhone 12 Pro Max 128GB graphite', price: 14500, delta: null, condition: 'working', seller: 'Иван (частник)', seen: '25.04 09:14', alert: false, zone: 'market_high', color: '#3F4855' },
    { id: 4823892, title: 'iPhone 12 Pro Max 256GB silver', price: 13200, delta: null, condition: 'working', seller: 'Studio M (компания)', seen: '25.04 08:47', alert: true, zone: 'alert', color: '#C8C9CD' },
    { id: 4823811, title: 'iPhone 12 Pro Max 128GB gold', price: 12800, delta: null, condition: 'working', seller: 'Артём (частник)', seen: '25.04 07:30', alert: true, zone: 'alert', isNew: true, color: '#E8D7B5' },
    { id: 4823799, title: 'iPhone 12 Pro Max 64GB blue', price: 11500, delta: null, condition: 'broken_screen', seller: 'Мобильный мир', seen: '25.04 06:12', alert: false, zone: 'market', color: '#1F3A6E' },
    { id: 4823654, title: 'iPhone 12 Pro Max 64GB graphite', price: 9800, delta: null, condition: 'blocked_icloud', seller: 'Дмитрий', seen: '25.04 04:55', alert: false, zone: 'market_low', color: '#3F4855' },
    { id: 4823432, title: 'iPhone 12 Pro Max 256GB pacific blue', price: 13400, delta: -7.6, condition: 'working', seller: 'Telecom Plus', seen: '25.04 02:18', alert: true, zone: 'alert', priceDrop: true, color: '#3D5A75' },
    { id: 4823200, title: 'iPhone 12 Pro Max 128GB silver', price: 12100, delta: null, condition: 'blocked_icloud', seller: 'Сергей', seen: '24.04 22:45', alert: false, zone: 'market', color: '#C8C9CD' },
    { id: 4823189, title: 'iPhone 12 Pro Max 512GB graphite', price: 16000, delta: null, condition: 'working', seller: 'Studio M', seen: '24.04 21:33', alert: false, zone: 'market_high', color: '#3F4855' },
    { id: 4823100, title: 'iPhone 12 Pro Max 128GB gold', price: 13050, delta: null, condition: 'working', seller: 'Алина (частник)', seen: '24.04 19:20', alert: true, zone: 'alert', color: '#E8D7B5' },
    { id: 4822987, title: 'iPhone 12 Pro Max 64GB blue', price: 8500, delta: null, condition: 'parts_only', seller: 'Запчасти 24', seen: '24.04 17:08', alert: false, zone: 'market_low', color: '#1F3A6E' },
    { id: 4822801, title: 'iPhone 12 Pro Max 256GB silver', price: 13380, delta: null, condition: 'broken_other', seller: 'Игорь', seen: '24.04 14:55', alert: false, zone: 'market', color: '#C8C9CD' },
    { id: 4822654, title: 'iPhone 12 Pro Max 128GB graphite', price: 12950, delta: null, condition: 'working', seller: 'Studio M', seen: '24.04 11:42', alert: true, zone: 'alert', color: '#3F4855' },
  ],

  metrics: {
    listings_24h: 12,
    new_24h: 4,
    in_alert: 7,
    in_alert_working: 5,
    notifications_24h: 4,
    median_clean: 13050,
    median_raw: 13015,
    median_delta_30d: -9.6,
    price_min: 8500,
    price_max: 16000,
    p25_clean: 12875,
    p75_clean: 13300,
    working_share: 41.7,
    working_share_delta: 5,
    avg_lifetime_h: 18.5,
    disappeared_24h: 3,
    llm_cost_24h: 2.40,
  },

  // distribution counts
  distribution: { working: 5, blocked_icloud: 3, broken_screen: 2, broken_other: 1, parts_only: 1 },

  // 30-day median(clean)
  history: [
    { d: '26.03', median: 14050, min: 9200, max: 18500 },
    { d: '27.03', median: 13980, min: 9100, max: 18400 },
    { d: '28.03', median: 14100, min: 9300, max: 18600 },
    { d: '29.03', median: 14020, min: 9200, max: 18500 },
    { d: '30.03', median: 13850, min: 9000, max: 18200 },
    { d: '31.03', median: 13750, min: 8900, max: 18100 },
    { d: '01.04', median: 13700, min: 8800, max: 18000 },
    { d: '02.04', median: 13800, min: 8950, max: 18100 },
    { d: '03.04', median: 13650, min: 8800, max: 17950 },
    { d: '04.04', median: 13580, min: 8700, max: 17800 },
    { d: '05.04', median: 13500, min: 8650, max: 17700 },
    { d: '06.04', median: 13400, min: 8600, max: 17600 },
    { d: '07.04', median: 13350, min: 8500, max: 17500 },
    { d: '08.04', median: 13200, min: 8450, max: 17300 },
    { d: '09.04', median: 13150, min: 8400, max: 17200 },
    { d: '10.04', median: 13080, min: 8350, max: 17100 },
    { d: '11.04', median: 13000, min: 8300, max: 17000 },
    { d: '12.04', median: 12950, min: 8200, max: 16900 },
    { d: '13.04', median: 12900, min: 8150, max: 16850 },
    { d: '14.04', median: 12850, min: 8100, max: 16800 },
    { d: '15.04', median: 12800, min: 8000, max: 16700 },
    { d: '16.04', median: 12750, min: 7950, max: 16650 },
    { d: '17.04', median: 12700, min: 7900, max: 16600 },
    { d: '18.04', median: 12650, min: 7850, max: 16550 },
    { d: '19.04', median: 12700, min: 7900, max: 16600 },
    { d: '20.04', median: 12750, min: 7950, max: 16700 },
    { d: '21.04', median: 12850, min: 8050, max: 16800 },
    { d: '22.04', median: 12950, min: 8150, max: 16900 },
    { d: '23.04', median: 13000, min: 8200, max: 16950 },
    { d: '24.04', median: 13050, min: 8250, max: 17000 },
    { d: '25.04', median: 13050, min: 8500, max: 16000 },
  ],

  events: [
    { time: '25.04 02:18', type: 'price_drop_listing', text: 'Лот #4823432 (256GB pacific blue) подешевел на 7.6%', delta: '14 500 → 13 400 ₽', icon: '↓' },
    { time: '24.04 19:20', type: 'historical_low', text: 'Лот #4823100 (128GB gold) — 13 050 ₽, ниже минимума за 30 дней', delta: 'min/30d', icon: '⊥' },
    { time: '24.04 03:45', type: 'condition_mix_change', text: 'Доля working лотов выросла с 32% → 45% за неделю', delta: '+13%', icon: '◐' },
    { time: '22.04 14:00', type: 'market_trend_down', text: 'Медиана рынка просела на 7.5% за неделю', delta: '13 800 → 12 750 ₽', icon: '↘' },
    { time: '20.04 11:30', type: 'supply_surge', text: 'Активных предложений +35% за неделю', delta: '28 → 35', icon: '⇈' },
    { time: '18.04 09:15', type: 'market_trend_down', text: 'Медиана рынка просела на 5.2% за неделю', delta: '14 100 → 13 350 ₽', icon: '↘' },
    { time: '17.04 16:42', type: 'price_dropped_into_alert', text: 'Лот #4822201 (256GB silver) вошёл в alert-зону снизу', delta: '13 480 ₽', icon: '↪' },
  ],
};

// helpers
window.AM_FMT = {
  price(n) {
    if (n == null) return '—';
    return n.toLocaleString('ru-RU').replace(/\u00A0/g, ' ') + ' ₽';
  },
  priceShort(n) {
    if (n >= 1000) return (n/1000).toFixed(n % 1000 === 0 ? 0 : 1) + 'K';
    return String(n);
  },
  num(n) { return n.toLocaleString('ru-RU').replace(/\u00A0/g, ' '); },
};

// condition meta
window.AM_COND = {
  working:        { cls: 'c-working',  trader: 'WORKING',     avito: 'Рабочий' },
  blocked_icloud: { cls: 'c-icloud',   trader: 'iCLOUD',      avito: 'iCloud-блок' },
  blocked_account:{ cls: 'c-account',  trader: 'ACC-BLOCK',   avito: 'Блок аккаунт' },
  not_starting:   { cls: 'c-notstart', trader: 'NO-START',    avito: 'Не включается' },
  broken_screen:  { cls: 'c-screen',   trader: 'BROKEN-SCR',  avito: 'Разбит экран' },
  broken_other:   { cls: 'c-other',    trader: 'BROKEN',      avito: 'Поломка' },
  parts_only:     { cls: 'c-parts',    trader: 'PARTS',       avito: 'На запчасти' },
  unknown:        { cls: 'c-unknown',  trader: '?',           avito: '?' },
};

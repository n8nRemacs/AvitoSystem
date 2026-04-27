/* global React, TopBar, Sidebar, AM_FMT */

function ScreenLogs({ theme }) {
  const [filter, setFilter] = React.useState('all');
  const [tab, setTab] = React.useState('runs');

  const levels = [
    { id: 'all', label: 'Все', count: 184 },
    { id: 'success', label: 'Успешные', count: 162, color: 'var(--positive)' },
    { id: 'warn', label: 'Warning', count: 18, color: 'var(--warning)' },
    { id: 'error', label: 'Errors', count: 4, color: 'var(--negative)' },
  ];

  const runs = [
    { t: '10:34:02', dur: '1.2s', profile: 'iPhone 12 Pro Max', level: 'success', code: 200, items: 12, newL: 1, llm: 0.0024, msg: 'Парсинг успешен · 12 лотов · +1 новый в alert' },
    { t: '10:29:01', dur: '0.9s', profile: 'MacBook Air M2', level: 'success', code: 200, items: 28, newL: 0, llm: 0.0058, msg: 'Парсинг успешен · 28 лотов' },
    { t: '10:24:00', dur: '1.4s', profile: 'AirPods Pro 2', level: 'success', code: 200, items: 18, newL: 0, llm: 0.0036, msg: 'Парсинг успешен · 18 лотов' },
    { t: '10:19:02', dur: '0.8s', profile: 'Apple Watch S9', level: 'success', code: 200, items: 22, newL: 2, llm: 0.0044, msg: 'Парсинг успешен · 22 лота · +2 новых' },
    { t: '10:14:08', dur: '4.2s', profile: 'iPhone 12 Pro Max', level: 'warn', code: 429, items: 0, newL: 0, llm: 0, msg: 'Rate limit. Ретрай через 5 мин (попытка 1/3)' },
    { t: '10:09:00', dur: '1.1s', profile: 'MacBook Air M2', level: 'success', code: 200, items: 28, newL: 0, llm: 0.0056, msg: 'Парсинг успешен · 28 лотов' },
    { t: '10:04:23', dur: '12.4s', profile: 'iPhone 12 Pro Max', level: 'error', code: 503, items: 0, newL: 0, llm: 0, msg: 'Avito 503. Все 3 ретрая упали. Пауза polling на 5 мин.' },
    { t: '09:59:01', dur: '1.0s', profile: 'AirPods Pro 2', level: 'success', code: 200, items: 18, newL: 0, llm: 0.0036, msg: 'Парсинг успешен · 18 лотов' },
    { t: '09:54:00', dur: '1.3s', profile: 'Apple Watch S9', level: 'success', code: 200, items: 22, newL: 0, llm: 0.0044, msg: 'Парсинг успешен · 22 лота' },
    { t: '09:49:08', dur: '6.8s', profile: 'iPhone 12 Pro Max', level: 'warn', code: 200, items: 12, newL: 0, llm: 0.0024, msg: 'Капча обнаружена → смена IP → парсинг успешен' },
  ];

  const events = [
    { t: '10:34:02', kind: 'alert_new', text: 'Лот #4823432 (iPhone 256GB pacific blue) — попал в alert-зону · -7.6%', tg: true },
    { t: '10:34:03', kind: 'tg_sent', text: 'Telegram-уведомление отправлено в @kostya_avito_bot · доставлено за 0.4s', tg: false },
    { t: '10:14:08', kind: 'system', text: 'Rate-limit от Avito (429). Polling iPhone профиля приостановлен на 5 мин', tg: false },
    { t: '10:04:23', kind: 'error', text: 'Avito вернул 503 после 3 ретраев. Polling iPhone профиля поставлен на паузу.', tg: true },
    { t: '09:49:08', kind: 'system', text: 'Капча на iPhone-запросе. Смена residential-IP → ms-3 → успех', tg: false },
    { t: '08:00:00', kind: 'cron', text: 'Daily cleanup: удалено 142 лота старше 90 дней', tg: false },
    { t: '07:32:00', kind: 'alert_drop', text: 'Лот #4822987 (iPhone 64GB blue) — выпал из активных (продан/удалён)', tg: false },
  ];

  const filtered = filter === 'all' ? runs : runs.filter(r => r.level === filter);

  return (
    <div className={`am-screen theme-${theme}`}>
      <TopBar theme={theme} />
      <Sidebar active="logs" />
      <div className="am-content scroll-y">
        <div className="am-page-h">
          <h1>Логи</h1>
          <div style={{display:'flex',gap:8}}>
            <button className="am-btn am-btn-sm">📥 Экспорт</button>
            <button className="am-btn am-btn-sm">🗑 Очистить старше 7д</button>
          </div>
        </div>

        {/* Health hero */}
        <div className="am-set-card am-logs-hero" style={{marginBottom:20}}>
          <div className="am-logs-hero-grid">
            <div>
              <div className="lbl">UPTIME · 24Ч</div>
              <div className="v" style={{color:'var(--positive)'}}>97.8%</div>
              <div className="sub">2 паузы по 5 мин</div>
            </div>
            <div>
              <div className="lbl">УСПЕШНОСТЬ ЗАПРОСОВ</div>
              <div className="v">88.0%</div>
              <div className="sub">162 / 184 · 4 errors</div>
            </div>
            <div>
              <div className="lbl">СРЕДНЕЕ ВРЕМЯ</div>
              <div className="v">1.4s</div>
              <div className="sub">p95 = 4.2s</div>
            </div>
            <div>
              <div className="lbl">ПОСЛЕДНЯЯ ОШИБКА</div>
              <div className="v" style={{fontSize:18}}>30 мин назад</div>
              <div className="sub">503 на iPhone-профиле</div>
            </div>
          </div>
          <div className="am-logs-bar">
            {Array.from({length:96}).map((_, i) => {
              const t = i / 96;
              const isErr = i === 76 || i === 71;
              const isWarn = i === 78 || i === 84 || i === 60;
              const cls = isErr ? 'err' : isWarn ? 'warn' : 'ok';
              return <span key={i} className={`am-bar-tick ${cls}`}/>;
            })}
          </div>
          <div className="am-logs-bar-axis">
            <span>−24ч</span><span>−18</span><span>−12</span><span>−6</span><span>сейчас</span>
          </div>
        </div>

        {/* Tabs */}
        <div className="am-settings-tabs">
          {[
            { id: 'runs', label: 'Запуски polling', icon: '🔄' },
            { id: 'events', label: 'События', icon: '📡' },
            { id: 'cron', label: 'Cron', icon: '⏱' },
          ].map(t => (
            <button key={t.id} className={`am-settings-tab ${tab === t.id ? 'active' : ''}`} onClick={() => setTab(t.id)}>
              <span style={{fontSize:14}}>{t.icon}</span><span>{t.label}</span>
            </button>
          ))}
        </div>

        {tab === 'runs' && (
          <>
            {/* Level filters */}
            <div style={{display:'flex',gap:8,marginBottom:16,alignItems:'center'}}>
              {levels.map(l => (
                <button
                  key={l.id}
                  className={`am-radio-pill ${filter === l.id ? 'active' : ''}`}
                  onClick={() => setFilter(l.id)}
                  style={{cursor:'pointer'}}
                >
                  {l.color && <span style={{width:8,height:8,background:l.color,borderRadius:'50%',display:'inline-block'}}></span>}
                  <span>{l.label}</span>
                  <span style={{color:'var(--text-muted)',fontSize:11,fontFamily:'var(--font-mono)'}}>{l.count}</span>
                </button>
              ))}
              <div style={{flex:1}}/>
              <input className="am-input" placeholder="Поиск по сообщению..." style={{maxWidth:280,fontSize:13}}/>
            </div>

            <div className="am-set-card" style={{padding:0,overflow:'hidden'}}>
              <table className="am-table am-logs-table">
                <thead>
                  <tr>
                    <th style={{width:110}}>Время</th>
                    <th style={{width:60}}>HTTP</th>
                    <th>Профиль</th>
                    <th style={{width:60,textAlign:'right'}}>Лотов</th>
                    <th style={{width:50,textAlign:'right'}}>Дл.</th>
                    <th style={{width:80,textAlign:'right'}}>LLM $</th>
                    <th>Сообщение</th>
                  </tr>
                </thead>
                <tbody>
                  {filtered.map((r, i) => (
                    <tr key={i} className={`am-log-row level-${r.level}`}>
                      <td style={{fontFamily:'var(--font-mono)',color:'var(--text-secondary)'}}>{r.t}</td>
                      <td>
                        <span className={`am-http-code c-${Math.floor(r.code/100)}xx`}>{r.code}</span>
                      </td>
                      <td>{r.profile}</td>
                      <td style={{textAlign:'right',fontFamily:'var(--font-mono)'}}>
                        {r.items > 0 ? r.items : '—'}
                        {r.newL > 0 && <span style={{color:'var(--positive)',fontSize:11,marginLeft:4}}>+{r.newL}</span>}
                      </td>
                      <td style={{textAlign:'right',fontFamily:'var(--font-mono)',color:'var(--text-muted)'}}>{r.dur}</td>
                      <td style={{textAlign:'right',fontFamily:'var(--font-mono)',color:'var(--text-muted)'}}>
                        {r.llm > 0 ? '$' + r.llm.toFixed(4) : '—'}
                      </td>
                      <td style={{color: r.level === 'error' ? 'var(--negative)' : r.level === 'warn' ? '#9C7800' : 'var(--text-secondary)',fontSize:13}}>
                        {r.msg}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <div style={{padding:'12px 20px',borderTop:'1px solid var(--border-soft)',fontSize:12,color:'var(--text-muted)',display:'flex',justifyContent:'space-between'}}>
                <span>Показано {filtered.length} из 184</span>
                <span>Загрузить ещё ↓</span>
              </div>
            </div>
          </>
        )}

        {tab === 'events' && (
          <div className="am-set-card" style={{padding:0}}>
            <div style={{padding:'4px 0'}}>
              {events.map((e, i) => {
                const ICON = {
                  alert_new: { i: '🎯', c: 'var(--positive)' },
                  alert_drop: { i: '↘', c: 'var(--text-muted)' },
                  tg_sent: { i: '✈', c: '#1989C5' },
                  system: { i: '⚙', c: '#9C7800' },
                  error: { i: '✕', c: 'var(--negative)' },
                  cron: { i: '⏱', c: 'var(--text-muted)' },
                }[e.kind];
                return (
                  <div key={i} className="am-event-row">
                    <div className="am-event-icon" style={{color: ICON.c}}>{ICON.i}</div>
                    <div className="am-event-time">{e.t}</div>
                    <div className="am-event-body">
                      <div>{e.text}</div>
                      {e.tg && <span className="am-pill" style={{background:'var(--brand-soft)',color:'#4d6b14',fontSize:10,padding:'2px 8px',marginTop:4,display:'inline-block'}}>→ Telegram</span>}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {tab === 'cron' && (
          <div className="am-set-card">
            <table className="am-table">
              <thead><tr><th>Job</th><th>Расписание</th><th>Последний запуск</th><th>Статус</th><th>Длит.</th></tr></thead>
              <tbody>
                <tr><td>polling.iphone</td><td style={{fontFamily:'var(--font-mono)'}}>*/5 * * * *</td><td>10:34</td><td><span className="am-pill am-pill-ok" style={{fontSize:11}}>ok</span></td><td style={{fontFamily:'var(--font-mono)'}}>1.2s</td></tr>
                <tr><td>polling.macbook</td><td style={{fontFamily:'var(--font-mono)'}}>*/5 * * * *</td><td>10:29</td><td><span className="am-pill am-pill-ok" style={{fontSize:11}}>ok</span></td><td style={{fontFamily:'var(--font-mono)'}}>0.9s</td></tr>
                <tr><td>cleanup.history</td><td style={{fontFamily:'var(--font-mono)'}}>0 8 * * *</td><td>08:00</td><td><span className="am-pill am-pill-ok" style={{fontSize:11}}>ok</span></td><td style={{fontFamily:'var(--font-mono)'}}>4.2s</td></tr>
                <tr><td>llm.cost-rollup</td><td style={{fontFamily:'var(--font-mono)'}}>0 0 * * *</td><td>00:00</td><td><span className="am-pill am-pill-ok" style={{fontSize:11}}>ok</span></td><td style={{fontFamily:'var(--font-mono)'}}>0.3s</td></tr>
                <tr><td>tg.daily-digest</td><td style={{fontFamily:'var(--font-mono)'}}>0 9 * * *</td><td>09:00</td><td><span className="am-pill am-pill-ok" style={{fontSize:11}}>ok</span></td><td style={{fontFamily:'var(--font-mono)'}}>0.6s</td></tr>
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}

window.ScreenLogs = ScreenLogs;

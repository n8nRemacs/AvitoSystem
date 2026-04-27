/* global React, TopBar, Sidebar, Kpi, ProfileCardCompact, MarketEventRow, ListingCard, AM_DATA */

function ScreenDashboard({ theme }) {
  const D = AM_DATA;
  const allProfiles = [
    { id: D.profile.id, name: D.profile.name, active: true, new24h: D.metrics.new_24h, median: D.metrics.median_clean, alert: D.metrics.in_alert, working: D.metrics.in_alert_working, mix: { working: 41.7, screen: 16.7, other: 8.3, parts: 8.3 } },
    ...D.otherProfiles,
  ];

  return (
    <div className={`am-screen theme-${theme}`}>
      <TopBar theme={theme} />
      <Sidebar active="dashboard" />
      <div className="am-content scroll-y">
        <div className="am-page-h">
          <h1>Дашборд</h1>
          <div style={{display:'flex',gap:8}}>
            <button className="am-btn am-btn-sm">Сегодня ▾</button>
            <button className="am-btn am-btn-primary am-btn-sm">+ Новый профиль</button>
          </div>
        </div>

        <div className="am-banner warn" style={{display:'none'}}>
          ⏸ Система на паузе с 25.04 14:32 — <span className="am-link">Возобновить</span>
        </div>

        <div className="am-kpi-row">
          <Kpi label="Активных профилей" value="3" delta="из 4" />
          <Kpi label="Лотов за 24ч" value="19" delta="+4 новых" deltaCls="pos" />
          <Kpi label="В alert-зоне" value="12" delta="working: 8" />
          <Kpi label="LLM расход / 24ч" value="$2.40" delta="classify·match" />
        </div>

        <div className="am-section">
          <div className="am-section-h">
            <span>Активные профили</span>
            <span className="am-link">→ Все профили</span>
          </div>
          <div style={{display:'grid', gridTemplateColumns:'1fr 1fr 1fr', gap:14}}>
            {allProfiles.slice(0,3).map(p => <ProfileCardCompact key={p.id} profile={p} theme={theme} />)}
          </div>
        </div>

        <div style={{display:'grid', gridTemplateColumns:'1.2fr 1fr', gap:14, marginTop:18}}>
          <div className="am-card">
            <div className="am-card-h">
              <h3>Последние market-события</h3>
              <span className="am-link">→ Смотреть все</span>
            </div>
            <div>
              {AM_DATA.events.slice(0,5).map((e,i) => <MarketEventRow key={i} event={e} theme={theme} />)}
            </div>
          </div>

          <div className="am-card">
            <div className="am-card-h">
              <h3>Лоты в alert-зоне</h3>
              <span className="am-link">→ К ленте</span>
            </div>
            <div style={{display:'flex',flexDirection:'column',gap:8}}>
              {AM_DATA.listings.filter(l => l.alert).slice(0,4).map(l => <ListingCard key={l.id} item={l} theme={theme} dense />)}
            </div>
          </div>
        </div>

        <div style={{marginTop:18}} className="am-state-note">
          <span className="lbl">Empty</span>Если профилей нет — большая иллюстрация по центру + CTA «+ Новый профиль».
          &nbsp;&nbsp;<span className="lbl">Loading</span>KPI и карточки превращаются в skeleton-плашки.
          &nbsp;&nbsp;<span className="lbl">System paused</span>Жёлтая полоса вверху (показана выше скрыто) — «Система на паузе с 25.04 14:32. [Возобновить]».
        </div>
      </div>
    </div>
  );
}

window.ScreenDashboard = ScreenDashboard;

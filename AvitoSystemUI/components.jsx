/* global React */
// Shared UI components for Avito Monitor screens.
// All theme-aware via CSS vars on parent .theme-trader / .theme-avito.

const { useState, useEffect, useRef } = React;

// ─── Topbar ──────────────────────────────────────────────────────────
function TopBar({ theme }) {
  return (
    <div className="am-topbar">
      <div className="am-logo">
        <div className="am-logo-mark">
          <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
            <path d="M2 11 L7 2 L12 11 Z" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round"/>
            <circle cx="7" cy="9" r="1.2" fill="currentColor"/>
          </svg>
        </div>
        <span>Avito Monitor</span>
        <span className="am-version">v1.2</span>
      </div>
      <div className="am-topbar-actions">
        <button className="am-btn am-btn-sm">
          <span style={{display:'inline-block', width:8, height:8, borderRadius:2, background:'var(--positive)'}}></span>
          Активна
        </button>
        <button className="am-btn am-btn-sm">⏸ Пауза</button>
        <button className="am-iconbtn">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
            <circle cx="12" cy="12" r="3"/>
            <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09a1.65 1.65 0 0 0-1-1.51 1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09a1.65 1.65 0 0 0 1.51-1 1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 1 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/>
          </svg>
        </button>
        <div style={{display:'flex',alignItems:'center',gap:8,paddingLeft:8,borderLeft:'1px solid var(--border)'}}>
          <div style={{width:24,height:24,borderRadius:'50%',background:'var(--surface-elev)',display:'grid',placeItems:'center',fontSize:11,fontWeight:600}}>K</div>
          <span style={{fontSize:12,color:'var(--text-secondary)'}}>kostya ▾</span>
        </div>
      </div>
    </div>
  );
}

// ─── Sidebar ─────────────────────────────────────────────────────────
const NAV_ITEMS = [
  { id: 'dashboard', label: 'Дашборд', icon: '📊' },
  { id: 'profiles', label: 'Профили', icon: '🎯', badge: '3' },
  { id: 'listings', label: 'Лоты', icon: '📦', badge: '12' },
  { id: 'prices', label: 'Цены', icon: '💰' },
  { id: 'logs', label: 'Логи', icon: '📜' },
  { id: 'settings', label: 'Настройки', icon: '⚙' },
];

function Sidebar({ active }) {
  return (
    <div className="am-sidebar">
      {NAV_ITEMS.map(it => (
        <div key={it.id} className={`am-nav-item ${active === it.id ? 'active' : ''}`}>
          <span className="am-nav-icon">{it.icon}</span>
          <span>{it.label}</span>
          {it.badge && <span className="am-badge">{it.badge}</span>}
        </div>
      ))}
      <div className="am-sidebar-footer">
        <div className="am-footer-row">
          <span>SYSTEM</span>
          <span className="v on">● ON</span>
        </div>
        <div className="am-footer-row">
          <span>LLM/24h</span>
          <span className="v">$2.40</span>
        </div>
        <div className="am-footer-row">
          <span>POLLED</span>
          <span className="v">10:34</span>
        </div>
      </div>
    </div>
  );
}

// ─── ConditionChip ───────────────────────────────────────────────────
function ConditionChip({ value, theme }) {
  const meta = AM_COND[value] || AM_COND.unknown;
  const label = theme === 'trader' ? meta.trader : meta.avito;
  return <span className={`am-chip ${meta.cls}`}>{label}</span>;
}

// ─── PriceTag ────────────────────────────────────────────────────────
function PriceTag({ value, delta }) {
  return (
    <span>
      <span className="am-price">{AM_FMT.price(value)}</span>
      {delta != null && (
        <span className={`am-price-delta ${delta < 0 ? 'neg' : 'pos'}`}>
          {delta < 0 ? '▼' : '▲'} {Math.abs(delta).toFixed(1)}%
        </span>
      )}
    </span>
  );
}

// ─── DualPriceRange ─────────────────────────────────────────────────
function DualPriceRange({ searchMin, searchMax, alertMin, alertMax, mini = false, currentMedian }) {
  // Map prices onto a [0%..100%] coordinate over the search span
  const range = searchMax - searchMin;
  const pct = (v) => Math.max(0, Math.min(100, ((v - searchMin) / range) * 100));
  const aMin = pct(alertMin);
  const aMax = pct(alertMax);
  const medPct = currentMedian != null ? pct(currentMedian) : null;

  return (
    <div className={`am-dpr ${mini ? 'am-dpr-mini' : ''}`}>
      <div className="am-dpr-track">
        <div className="am-dpr-search" style={{ left: '0%', right: '0%' }} />
        <div className="am-dpr-alert" style={{ left: `${aMin}%`, width: `${aMax - aMin}%` }} />
        {/* tick labels above */}
        <div className="am-dpr-tick" style={{ left: '0%' }}>
          <div className="v">{AM_FMT.priceShort(searchMin)}</div>
        </div>
        <div className="am-dpr-tick" style={{ left: `${aMin}%` }}>
          <div className="v">{AM_FMT.priceShort(alertMin)}</div>
        </div>
        <div className="am-dpr-tick" style={{ left: `${aMax}%` }}>
          <div className="v">{AM_FMT.priceShort(alertMax)}</div>
        </div>
        <div className="am-dpr-tick" style={{ left: '100%' }}>
          <div className="v">{AM_FMT.priceShort(searchMax)}</div>
        </div>
        {/* median marker */}
        {medPct != null && (
          <div style={{position:'absolute', top:-4, bottom:-4, left:`${medPct}%`, width:2, background:'var(--accent)', borderRadius:1}}>
            <div style={{position:'absolute', bottom:'100%', left:'50%', transform:'translateX(-50%)', fontSize:10, fontFamily:'var(--font-mono)', color:'var(--accent)', whiteSpace:'nowrap', marginBottom:2}}>★ {AM_FMT.priceShort(currentMedian)}</div>
          </div>
        )}
        {/* labels below */}
        {!mini && (
          <>
            <div className="am-dpr-label" style={{ left: '50%' }}>SEARCH ZONE</div>
            <div className="am-dpr-label" style={{ left: `${(aMin + aMax)/2}%`, color: 'var(--positive)' }}>ALERT</div>
          </>
        )}
      </div>
    </div>
  );
}

// ─── Listing thumbnail (SVG iPhone silhouette tinted) ────────────────
function ListingThumb({ color = '#3F4855', alert = false, isNew = false }) {
  return (
    <div className="am-listing-thumb" style={{background: color}}>
      <svg width="36" height="56" viewBox="0 0 36 56" fill="none">
        <rect x="2" y="2" width="32" height="52" rx="5" stroke="rgba(255,255,255,0.4)" strokeWidth="1.5"/>
        <rect x="5" y="6" width="26" height="38" rx="2" fill="rgba(255,255,255,0.12)"/>
        <circle cx="18" cy="49" r="1.5" fill="rgba(255,255,255,0.3)"/>
        <rect x="10" y="3.5" width="8" height="2" rx="1" fill="rgba(0,0,0,0.4)"/>
        <rect x="22" y="9" width="4" height="4" rx="1" fill="rgba(255,255,255,0.6)"/>
      </svg>
      {isNew && (
        <div style={{position:'absolute', top:4, right:4, background:'var(--positive)', color:'#fff', fontSize:8, fontWeight:700, padding:'2px 4px', borderRadius:2, fontFamily:'var(--font-mono)'}}>NEW</div>
      )}
    </div>
  );
}

// ─── ListingCard ─────────────────────────────────────────────────────
function ListingCard({ item, theme, dense = false }) {
  return (
    <div className={`am-listing ${item.zone !== 'alert' ? 'muted' : ''}`}>
      <ListingThumb color={item.color} alert={item.alert} isNew={item.isNew} />
      <div className="am-listing-body">
        <div className="am-listing-title">{item.title}</div>
        <div className="am-listing-row1">
          <PriceTag value={item.price} delta={item.delta} />
          <ConditionChip value={item.condition} theme={theme} />
          {item.alert && (
            <span className="am-zone-dot">
              <span className="am-dot on"></span>
              {theme === 'trader' ? 'ALERT' : 'В alert-зоне'}
            </span>
          )}
          {!item.alert && (
            <span className="am-zone-dot market">
              <span className="am-dot off"></span>
              {theme === 'trader' ? 'MARKET' : 'Рынок'}
            </span>
          )}
        </div>
        <div className="am-listing-meta">
          <span>{item.seller}</span>
          <span className="sep">·</span>
          <span className="mono">#{item.id}</span>
          <span className="sep">·</span>
          <span className="mono">{item.seen}</span>
        </div>
      </div>
      <div className="am-listing-actions">
        <button className="am-iconbtn">⋯</button>
      </div>
    </div>
  );
}

// ─── KPI card ────────────────────────────────────────────────────────
function Kpi({ label, value, delta, deltaCls }) {
  return (
    <div className="am-kpi">
      <div className="am-kpi-label">{label}</div>
      <div className="am-kpi-value">{value}</div>
      {delta && <div className={`am-kpi-delta ${deltaCls || ''}`}>{delta}</div>}
    </div>
  );
}

// ─── ProfileCardCompact ──────────────────────────────────────────────
function ProfileCardCompact({ profile, theme, primary = false }) {
  const colorMix = profile.mix || { working: 41.7, screen: 16.7, other: 16.7, parts: 16.7 };
  return (
    <div className="am-profcard">
      <div className="am-profcard-h">
        <div>
          <div style={{display:'flex',alignItems:'center',gap:8}}>
            <span className={`am-dot ${profile.active ? 'on' : 'off'}`}></span>
            <span className="am-profcard-name">{profile.name}</span>
          </div>
          <div className="am-profcard-sub">
            {profile.active ? 'active' : 'paused'} · {profile.poll || '5 мин'} · Apple / Москва
          </div>
        </div>
        <button className="am-iconbtn">⋯</button>
      </div>

      <div className="am-profcard-kpis">
        <div className="am-profcard-kpi">
          <span>Новых 24ч</span>
          <span className="v">{profile.new24h}</span>
        </div>
        <div className="am-profcard-kpi">
          <span>В alert-зоне</span>
          <span className="v">{profile.alert}{profile.working != null && <span style={{fontSize:11,color:'var(--text-muted)',fontWeight:400}}> / {profile.working} work</span>}</span>
        </div>
        <div className="am-profcard-kpi">
          <span>Медиана</span>
          <span className="v">{AM_FMT.priceShort(profile.median)}</span>
        </div>
      </div>

      {/* mini condition mix bar */}
      <div>
        <div className="am-mixbar">
          <div className="am-mixbar-seg" style={{width: `${colorMix.working}%`, background:'var(--positive)'}}></div>
          <div className="am-mixbar-seg" style={{width: `${colorMix.screen || 0}%`, background:'var(--negative)'}}></div>
          <div className="am-mixbar-seg" style={{width: `${colorMix.other || 0}%`, background:'var(--purple)'}}></div>
          <div className="am-mixbar-seg" style={{width: `${colorMix.parts || 0}%`, background:'var(--text-muted)'}}></div>
        </div>
        <div style={{display:'flex',justifyContent:'space-between',fontSize:10,color:'var(--text-muted)',marginTop:4,fontFamily: theme === 'trader' ? 'var(--font-mono)' : 'inherit'}}>
          <span>working {colorMix.working}%</span>
          <span>broken {(colorMix.screen||0) + (colorMix.other||0)}%</span>
          <span>parts {colorMix.parts || 0}%</span>
        </div>
      </div>
    </div>
  );
}

// ─── MarketEventRow ──────────────────────────────────────────────────
function MarketEventRow({ event, theme }) {
  return (
    <div className="am-event-row">
      <div className="am-event-icon">{event.icon}</div>
      <div className="am-event-time">{event.time}</div>
      <div className="am-event-headline">{event.text}</div>
      <div className="am-event-delta">{event.delta}</div>
    </div>
  );
}

// Make available globally
Object.assign(window, {
  TopBar, Sidebar, ConditionChip, PriceTag, DualPriceRange,
  ListingCard, ListingThumb, Kpi, ProfileCardCompact, MarketEventRow,
});

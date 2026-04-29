/* global React, TopBar, Sidebar, AM_FMT, AM_DATA */

function ScreenPrices({ theme }) {
  const [period, setPeriod] = React.useState('30d');
  const [view, setView] = React.useState('table');

  // Cross-profile price ranking — synthetic
  const profiles = [
    { id: 'p1', name: 'iPhone 12 Pro Max до 13.5K', median: 13050, deltaW: -2.3, deltaM: -9.6, min: 8500, max: 16000, supply: 12, alert: 7, trend: 'down', spark: [142, 138, 135, 133, 132, 131, 130, 130, 131, 130, 129, 128, 130, 130, 130, 131, 130, 130, 131, 130, 130] },
    { id: 'p2', name: 'MacBook Air M2 до 75K', median: 68500, deltaW: -1.8, deltaM: -4.2, min: 52000, max: 89000, supply: 28, alert: 4, trend: 'down', spark: [715, 712, 708, 705, 700, 695, 692, 690, 688, 685, 685, 686, 687, 685, 684, 685, 686, 685, 685, 685, 685] },
    { id: 'p3', name: 'AirPods Pro 2 до 12K', median: 10500, deltaW: 0.5, deltaM: 1.2, min: 6800, max: 14500, supply: 18, alert: 0, trend: 'flat', spark: [104, 105, 105, 104, 104, 105, 105, 106, 105, 105, 104, 105, 105, 105, 105, 106, 105, 105, 105, 105, 105] },
    { id: 'p4', name: 'Apple Watch Series 9 до 25K', median: 22300, deltaW: -3.1, deltaM: -8.4, min: 14000, max: 32000, supply: 22, alert: 6, trend: 'down', spark: [243, 240, 238, 235, 232, 230, 228, 227, 225, 224, 223, 223, 222, 223, 223, 223, 223, 223, 223, 223, 223] },
  ];

  const totals = {
    activeProfiles: profiles.length,
    totalListings: profiles.reduce((s, p) => s + p.supply, 0),
    inAlert: profiles.reduce((s, p) => s + p.alert, 0),
    avgDeltaM: -5.3,
  };

  return (
    <div className={`am-screen theme-${theme}`}>
      <TopBar theme={theme} />
      <Sidebar active="prices" />
      <div className="am-content scroll-y">
        <div className="am-page-h">
          <h1>Цены — кросс-профильный обзор</h1>
          <div style={{display:'flex',gap:8}}>
            <div className="am-radio-row">
              {[['7d','7д'],['30d','30д'],['90d','90д']].map(([v,l]) => (
                <label key={v} className={`am-radio-pill ${period === v ? 'active' : ''}`}>
                  <input type="radio" name="prices-period" checked={period === v} onChange={() => setPeriod(v)}/>
                  <span>{l}</span>
                </label>
              ))}
            </div>
            <button className="am-btn am-btn-sm">⬇ CSV</button>
          </div>
        </div>

        {/* KPI strip */}
        <div className="am-kpi-grid" style={{gridTemplateColumns:'repeat(4, 1fr)', gap:12, marginBottom:20}}>
          <div className="am-kpi"><div className="am-kpi-lbl">ПРОФИЛЕЙ</div><div className="am-kpi-v">{totals.activeProfiles}</div><div className="am-kpi-sub">отслеживаются</div></div>
          <div className="am-kpi"><div className="am-kpi-lbl">ВСЕГО ЛОТОВ</div><div className="am-kpi-v">{totals.totalListings}</div><div className="am-kpi-sub">в активном пуле</div></div>
          <div className="am-kpi"><div className="am-kpi-lbl">В ALERT-ЗОНЕ</div><div className="am-kpi-v" style={{color:'var(--negative)'}}>{totals.inAlert}</div><div className="am-kpi-sub">по всем профилям</div></div>
          <div className="am-kpi"><div className="am-kpi-lbl">МЕДИАНА · 30Д</div><div className="am-kpi-v" style={{color:'var(--positive)'}}>{totals.avgDeltaM}%</div><div className="am-kpi-sub">взвешенная по supply</div></div>
        </div>

        <div className="am-set-card" style={{padding:0, overflow:'hidden'}}>
          <div style={{display:'flex',justifyContent:'space-between',alignItems:'center',padding:'16px 20px',borderBottom:'1px solid var(--border-soft)'}}>
            <div>
              <div className="am-set-card-title">Профили по динамике цены</div>
              <div className="am-set-card-sub" style={{marginTop:2}}>Сортировка по падению медианы за 30 дней</div>
            </div>
            <div style={{display:'flex',gap:6}}>
              <button className={`am-tbtn ${view==='table'?'active':''}`} onClick={()=>setView('table')}>📋 Таблица</button>
              <button className={`am-tbtn ${view==='cards'?'active':''}`} onClick={()=>setView('cards')}>▦ Карточки</button>
            </div>
          </div>

          {view === 'table' && (
            <table className="am-table am-prices-table">
              <thead>
                <tr>
                  <th>Профиль</th>
                  <th style={{textAlign:'right'}}>Медиана</th>
                  <th style={{textAlign:'right'}}>Δ 7д</th>
                  <th style={{textAlign:'right'}}>Δ 30д</th>
                  <th>Тренд</th>
                  <th style={{textAlign:'right'}}>Min — Max</th>
                  <th style={{textAlign:'right'}}>Supply</th>
                  <th style={{textAlign:'right'}}>Alert</th>
                </tr>
              </thead>
              <tbody>
                {profiles.map(p => (
                  <tr key={p.id} className="am-prices-row">
                    <td className="am-prices-name">
                      <div style={{display:'flex',alignItems:'center',gap:10}}>
                        <span className={`am-trend-dot ${p.trend}`}></span>
                        {p.name}
                      </div>
                    </td>
                    <td style={{textAlign:'right',fontWeight:600}}>{AM_FMT.price(p.median)}</td>
                    <td style={{textAlign:'right',color: p.deltaW < 0 ? 'var(--positive)' : p.deltaW > 0 ? 'var(--negative)' : 'var(--text-muted)'}}>
                      {p.deltaW > 0 ? '+' : ''}{p.deltaW.toFixed(1)}%
                    </td>
                    <td style={{textAlign:'right',fontWeight:600,color: p.deltaM < 0 ? 'var(--positive)' : p.deltaM > 0 ? 'var(--negative)' : 'var(--text-muted)'}}>
                      {p.deltaM > 0 ? '+' : ''}{p.deltaM.toFixed(1)}%
                    </td>
                    <td><Sparkline data={p.spark} trend={p.trend} /></td>
                    <td style={{textAlign:'right',color:'var(--text-secondary)'}}>{AM_FMT.priceShort(p.min)} — {AM_FMT.priceShort(p.max)}</td>
                    <td style={{textAlign:'right'}}>{p.supply}</td>
                    <td style={{textAlign:'right'}}>
                      {p.alert > 0 ? <span className="am-pill" style={{background:'#FFE5E5',color:'#C92533',padding:'2px 8px',fontSize:11,fontWeight:600}}>{p.alert}</span> : <span style={{color:'var(--text-muted)'}}>—</span>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}

          {view === 'cards' && (
            <div style={{padding:20,display:'grid',gridTemplateColumns:'1fr 1fr',gap:16}}>
              {profiles.map(p => (
                <div key={p.id} className="am-set-card" style={{padding:16,margin:0}}>
                  <div style={{display:'flex',justifyContent:'space-between',alignItems:'flex-start',marginBottom:12}}>
                    <div>
                      <div style={{fontWeight:600,fontSize:14}}>{p.name}</div>
                      <div style={{fontSize:12,color:'var(--text-muted)',marginTop:2}}>{p.supply} лотов · {p.alert} в alert</div>
                    </div>
                    <span className={`am-trend-dot ${p.trend}`} style={{width:10,height:10}}></span>
                  </div>
                  <div style={{display:'flex',justifyContent:'space-between',alignItems:'baseline',marginBottom:8}}>
                    <div style={{fontSize:24,fontWeight:700,fontFamily:'var(--font-mono)'}}>{AM_FMT.price(p.median)}</div>
                    <div style={{fontSize:14,fontWeight:600,color: p.deltaM < 0 ? 'var(--positive)' : 'var(--negative)'}}>
                      {p.deltaM > 0 ? '+' : ''}{p.deltaM.toFixed(1)}% · 30д
                    </div>
                  </div>
                  <Sparkline data={p.spark} trend={p.trend} large />
                </div>
              ))}
            </div>
          )}
        </div>

        <div style={{display:'grid',gridTemplateColumns:'1fr 1fr',gap:16,marginTop:20}}>
          <div className="am-set-card">
            <div className="am-set-card-title" style={{marginBottom:14}}>Самые сильные движения · {period}</div>
            <div style={{display:'flex',flexDirection:'column',gap:10}}>
              {[
                { p: 'Apple Watch Series 9 до 25K', d: -8.4, n: '24.04 17:08' },
                { p: 'iPhone 12 Pro Max до 13.5K', d: -9.6, n: '22.04 14:00' },
                { p: 'MacBook Air M2 до 75K', d: -4.2, n: '20.04 09:30' },
                { p: 'AirPods Pro 2 до 12K', d: 1.2, n: '19.04 11:15' },
              ].map((m, i) => (
                <div key={i} style={{display:'flex',alignItems:'center',gap:12,padding:'8px 0',borderBottom: i<3 ? '1px solid var(--border-soft)' : 'none'}}>
                  <span style={{fontSize:18,color: m.d < 0 ? 'var(--positive)' : 'var(--negative)'}}>{m.d < 0 ? '↘' : '↗'}</span>
                  <div style={{flex:1,minWidth:0}}>
                    <div style={{fontSize:14,fontWeight:500}}>{m.p}</div>
                    <div style={{fontSize:11,color:'var(--text-muted)',fontFamily:'var(--font-mono)'}}>{m.n}</div>
                  </div>
                  <span style={{fontWeight:600,color: m.d < 0 ? 'var(--positive)' : 'var(--negative)'}}>{m.d > 0 ? '+' : ''}{m.d.toFixed(1)}%</span>
                </div>
              ))}
            </div>
          </div>

          <div className="am-set-card">
            <div className="am-set-card-title" style={{marginBottom:14}}>Корреляции профилей</div>
            <div style={{fontSize:13,color:'var(--text-muted)',marginBottom:12}}>Когда iPhone дешевеет, MacBook идёт следом — лаг 4-7 дней.</div>
            <table className="am-corr-table">
              <thead>
                <tr><th></th><th>iPhone</th><th>MBA</th><th>AirPods</th><th>Watch</th></tr>
              </thead>
              <tbody>
                <tr><td>iPhone</td><td className="c-1">1.00</td><td className="c-83">0.83</td><td className="c-21">0.21</td><td className="c-71">0.71</td></tr>
                <tr><td>MBA</td><td className="c-83">0.83</td><td className="c-1">1.00</td><td className="c-15">0.15</td><td className="c-58">0.58</td></tr>
                <tr><td>AirPods</td><td className="c-21">0.21</td><td className="c-15">0.15</td><td className="c-1">1.00</td><td className="c-32">0.32</td></tr>
                <tr><td>Watch</td><td className="c-71">0.71</td><td className="c-58">0.58</td><td className="c-32">0.32</td><td className="c-1">1.00</td></tr>
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
}

function Sparkline({ data, trend, large }) {
  const w = large ? 320 : 140;
  const h = large ? 50 : 28;
  const min = Math.min(...data), max = Math.max(...data);
  const range = max - min || 1;
  const points = data.map((v, i) => {
    const x = (i / (data.length - 1)) * w;
    const y = h - ((v - min) / range) * (h - 4) - 2;
    return `${x},${y}`;
  }).join(' ');
  const color = trend === 'down' ? '#2EBF5C' : trend === 'up' ? '#DC3545' : '#8C95A1';
  return (
    <svg width={w} height={h} style={{display:'block'}}>
      <polyline points={points} fill="none" stroke={color} strokeWidth="1.5" strokeLinejoin="round" strokeLinecap="round"/>
      <circle cx={(data.length - 1) / (data.length - 1) * w} cy={h - ((data[data.length-1] - min) / range) * (h - 4) - 2} r="2.5" fill={color}/>
    </svg>
  );
}

window.ScreenPrices = ScreenPrices;

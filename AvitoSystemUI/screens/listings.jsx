/* global React, TopBar, Sidebar, ListingCard, AM_DATA */

function ScreenListings({ theme }) {
  const D = AM_DATA;

  return (
    <div className={`am-screen theme-${theme}`}>
      <TopBar theme={theme}/>
      <Sidebar active="listings"/>
      <div className="am-content scroll-y">
        <div className="am-page-h">
          <div>
            <h1>Лоты</h1>
            <div style={{fontSize:12,color:'var(--text-secondary)',marginTop:4}}>
              <span className="mono">{D.listings.length}</span> лотов · <span className="mono" style={{color:'var(--positive)'}}>{D.listings.filter(l=>l.alert).length}</span> в alert · обновлено 25.04 10:34
            </div>
          </div>
          <div style={{display:'flex',gap:8}}>
            <button className="am-btn am-btn-sm">📤 Экспорт CSV</button>
            <button className="am-btn am-btn-sm">🔄 Обновить</button>
          </div>
        </div>

        {/* Filters */}
        <div className="am-card" style={{marginBottom:14}}>
          <div style={{display:'flex',flexDirection:'column',gap:10}}>
            <div className="am-chips-row">
              <span style={{fontSize:11, color:'var(--text-muted)', marginRight:6, fontFamily: theme==='trader'?'var(--font-mono)':'inherit', textTransform: theme==='trader'?'uppercase':'none'}}>Профиль</span>
              <button className="am-fchip">Все</button>
              <button className="am-fchip active">iPhone 12 Pro Max до 13.5K</button>
              <button className="am-fchip">MacBook Air M2</button>
              <button className="am-fchip">Apple Watch S9</button>
            </div>
            <div className="am-chips-row">
              <span style={{fontSize:11, color:'var(--text-muted)', marginRight:6, fontFamily: theme==='trader'?'var(--font-mono)':'inherit', textTransform: theme==='trader'?'uppercase':'none'}}>Состояние</span>
              <button className="am-fchip active">Рабочий</button>
              <button className="am-fchip">iCloud-блок</button>
              <button className="am-fchip">Разбит экран</button>
              <button className="am-fchip">Поломка</button>
              <button className="am-fchip">На запчасти</button>
            </div>
            <div className="am-chips-row">
              <span style={{fontSize:11, color:'var(--text-muted)', marginRight:6, fontFamily: theme==='trader'?'var(--font-mono)':'inherit', textTransform: theme==='trader'?'uppercase':'none'}}>Зона</span>
              <button className="am-fchip active">● Alert</button>
              <button className="am-fchip">Market data</button>
              <button className="am-fchip">Все</button>
              <span style={{flex:1}}></span>
              <span style={{fontSize:11, color:'var(--text-muted)', marginRight:6, fontFamily: theme==='trader'?'var(--font-mono)':'inherit', textTransform: theme==='trader'?'uppercase':'none'}}>Период</span>
              <button className="am-fchip">24ч</button>
              <button className="am-fchip active">7д</button>
              <button className="am-fchip">30д</button>
              <button className="am-fchip">Все</button>
            </div>
          </div>
        </div>

        {/* Sort */}
        <div style={{display:'flex',justifyContent:'space-between',alignItems:'center',marginBottom:10,fontSize:12,color:'var(--text-secondary)'}}>
          <div>Найдено: <span className="mono" style={{color:'var(--text-primary)',fontWeight:600}}>12</span> · в alert: <span className="mono" style={{color:'var(--positive)',fontWeight:600}}>5</span> (working)</div>
          <div className="am-chips-row">
            <span style={{fontSize:11, color:'var(--text-muted)'}}>Сорт.:</span>
            <button className="am-fchip active">По дате ↓</button>
            <button className="am-fchip">По цене</button>
            <button className="am-fchip">По дельте</button>
          </div>
        </div>

        {/* Listings */}
        <div style={{display:'flex',flexDirection:'column',gap:8}}>
          {D.listings.map(l => <ListingCard key={l.id} item={l} theme={theme}/>)}
        </div>

        <div style={{textAlign:'center',marginTop:14}}>
          <button className="am-btn am-btn-sm">Загрузить ещё</button>
        </div>

        <div className="am-state-note" style={{marginTop:14}}>
          <span className="lbl">Empty</span>«Пока нет лотов — запусти прогон профиля».
          &nbsp;&nbsp;<span className="lbl">Loading more</span>skeleton-карточки внизу.
          &nbsp;&nbsp;<span className="lbl">Muted</span>лоты вне alert-зоны приглушены до 55% opacity для быстрого сканирования.
        </div>
      </div>
    </div>
  );
}

window.ScreenListings = ScreenListings;

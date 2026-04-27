/* global React, TopBar, Sidebar, DualPriceRange, ConditionChip, AM_DATA */

function ScreenProfileCreate({ theme }) {
  const P = AM_DATA.profile;

  return (
    <div className={`am-screen theme-${theme}`}>
      <TopBar theme={theme} />
      <Sidebar active="profiles" />
      <div className="am-content scroll-y">
        <div className="am-page-h">
          <h1>Новый профиль поиска</h1>
          <div style={{display:'flex',gap:8}}>
            <button className="am-btn am-btn-sm">Отмена</button>
            <button className="am-btn am-btn-primary am-btn-sm">Сохранить и запустить</button>
          </div>
        </div>

        {/* Step 1: URL */}
        <div className="am-step">
          <div className="am-step-h">
            <div className="am-step-num">1</div>
            <div className="am-step-title">URL поиска Avito</div>
          </div>
          <div style={{display:'flex',gap:8}}>
            <input className="am-input" defaultValue={P.avito_search_url} style={{flex:1}}/>
            <button className="am-btn">Парсить</button>
          </div>
          <div className="am-parsed">
            <div className="am-parsed-row"><span className="am-parsed-label">📂 Категория</span><span className="am-parsed-val">{P.parsed_category}</span></div>
            <div className="am-parsed-row"><span className="am-parsed-label">🏷️ Бренд</span><span className="am-parsed-val">{P.parsed_brand}</span></div>
            <div className="am-parsed-row"><span className="am-parsed-label">📱 Модель</span><span className="am-parsed-val">{P.parsed_model}</span></div>
            <div className="am-parsed-row"><span className="am-parsed-label">🌍 Регион</span><span className="am-parsed-val">{P.region_slug}</span></div>
            <div className="am-parsed-row"><span className="am-parsed-label">💰 Цена</span><span className="am-parsed-val">11 000 – 13 500 ₽</span></div>
          </div>
          <div className="am-state-note" style={{marginTop:10}}>
            <span className="lbl">Error</span>«URL не похож на Avito-поиск. Скопируй из адресной строки веб-Avito.»
          </div>
        </div>

        {/* Step 2: Name */}
        <div className="am-step">
          <div className="am-step-h">
            <div className="am-step-num">2</div>
            <div className="am-step-title">Имя профиля</div>
          </div>
          <input className="am-input" defaultValue={P.name}/>
          <div style={{fontSize:11,color:'var(--text-muted)',marginTop:6}}>auto-предложено из распарсенного URL</div>
        </div>

        {/* Step 3: Dual price range — STAR */}
        <div className="am-step" style={{borderColor:'var(--accent)', boxShadow: theme === 'trader' ? '0 0 0 1px color-mix(in srgb, var(--accent) 30%, transparent)' : '0 1px 3px rgba(151, 207, 38, 0.15)'}}>
          <div className="am-step-h">
            <div className="am-step-num">3</div>
            <div className="am-step-title">Двойная вилка цен ⭐</div>
          </div>

          <div style={{display:'grid', gridTemplateColumns:'1fr 1fr', gap:18, marginBottom:8}}>
            <div>
              <div style={{fontSize:12, color:'var(--text-secondary)', marginBottom:6, fontWeight:500}}>Alert-вилка <span style={{color:'var(--text-muted)',fontWeight:400}}>(в мессенджер)</span></div>
              <div style={{display:'flex', gap:8}}>
                <div style={{flex:1}}>
                  <div style={{fontSize:10, color:'var(--text-muted)', marginBottom:2, fontFamily: theme==='trader'?'var(--font-mono)':'inherit'}}>pmin</div>
                  <input className="am-input" defaultValue="11 000"/>
                </div>
                <div style={{flex:1}}>
                  <div style={{fontSize:10, color:'var(--text-muted)', marginBottom:2, fontFamily: theme==='trader'?'var(--font-mono)':'inherit'}}>pmax</div>
                  <input className="am-input" defaultValue="13 500"/>
                </div>
              </div>
            </div>
            <div>
              <div style={{fontSize:12, color:'var(--text-secondary)', marginBottom:6, fontWeight:500}}>Search-вилка <span style={{color:'var(--text-muted)',fontWeight:400}}>(±25% по умолч.)</span></div>
              <div style={{display:'flex', gap:8}}>
                <div style={{flex:1}}>
                  <div style={{fontSize:10, color:'var(--text-muted)', marginBottom:2, fontFamily: theme==='trader'?'var(--font-mono)':'inherit'}}>pmin</div>
                  <input className="am-input" defaultValue="8 250"/>
                </div>
                <div style={{flex:1}}>
                  <div style={{fontSize:10, color:'var(--text-muted)', marginBottom:2, fontFamily: theme==='trader'?'var(--font-mono)':'inherit'}}>pmax</div>
                  <input className="am-input" defaultValue="16 875"/>
                </div>
              </div>
              <label className="am-check" style={{marginTop:8, fontSize:12}}>
                <input type="checkbox"/> Расширить до ±50% от alert
              </label>
            </div>
          </div>

          <DualPriceRange searchMin={P.search_min_price} searchMax={P.search_max_price} alertMin={P.alert_min_price} alertMax={P.alert_max_price} />

          <div className="am-helper">
            💡 Search-вилка нужна чтобы видеть рынок шире alert и считать тренды без искажений при просадке цен.
          </div>
        </div>

        {/* Step 4-7 collapsed */}
        <div style={{display:'grid', gridTemplateColumns:'1fr 1fr', gap:14}}>
          <div className="am-step">
            <div className="am-step-h">
              <div className="am-step-num">4</div>
              <div className="am-step-title">Переопределения</div>
              <span style={{marginLeft:'auto',color:'var(--text-muted)',fontSize:12}}>▾</span>
            </div>
            <div style={{display:'flex',flexDirection:'column',gap:10}}>
              <div className="am-input-row"><label>Регион</label><select className="am-select" style={{flex:1}}><option>Москва</option></select></div>
              <div className="am-input-row"><label>Сорт.</label><select className="am-select" style={{flex:1}}><option>По дате</option></select></div>
              <label className="am-check"><input type="checkbox"/> Только с доставкой</label>
            </div>
          </div>

          <div className="am-step">
            <div className="am-step-h">
              <div className="am-step-num">6</div>
              <div className="am-step-title">Расписание</div>
            </div>
            <div style={{display:'flex',flexDirection:'column',gap:10}}>
              <div className="am-input-row"><label>Интервал</label><select className="am-select" style={{flex:1}}><option>5 минут</option></select></div>
              <div className="am-input-row" style={{fontSize:12}}>
                <label>Пн-Пт</label>
                <input className="am-input" defaultValue="09:00" style={{flex:1}}/>
                <span style={{color:'var(--text-muted)'}}>—</span>
                <input className="am-input" defaultValue="23:00" style={{flex:1}}/>
              </div>
              <div className="am-input-row" style={{fontSize:12}}>
                <label>Сб-Вс</label>
                <input className="am-input" defaultValue="10:00" style={{flex:1}}/>
                <span style={{color:'var(--text-muted)'}}>—</span>
                <input className="am-input" defaultValue="22:00" style={{flex:1}}/>
              </div>
            </div>
          </div>
        </div>

        {/* Step 5: LLM */}
        <div className="am-step">
          <div className="am-step-h">
            <div className="am-step-num">5</div>
            <div className="am-step-title">LLM-критерии и фильтр состояния</div>
          </div>
          <div style={{fontSize:12, color:'var(--text-secondary)', marginBottom:8}}>Допустимые состояния</div>
          <div style={{display:'flex',flexWrap:'wrap',gap:8,marginBottom:14}}>
            {Object.entries(AM_COND).map(([k, v]) => {
              const isOn = k === 'working';
              return (
                <label key={k} className="am-fchip" style={{cursor:'pointer'}}>
                  <input type="checkbox" defaultChecked={isOn} style={{margin:0}}/>
                  <ConditionChip value={k} theme={theme}/>
                </label>
              );
            })}
          </div>
          <div style={{fontSize:12, color:'var(--text-secondary)', marginBottom:8}}>Произвольные критерии</div>
          <textarea className="am-textarea" rows="3" defaultValue="Аккумулятор не ниже 85%, без серьёзных царапин на корпусе, не реплика. Принимаются мелкие потёртости и сколы краски."/>
          <div style={{display:'flex', gap:14, marginTop:10, flexWrap:'wrap'}}>
            <label className="am-check"><input type="checkbox" defaultChecked/> Анализировать фото (visual LLM)</label>
            <div className="am-input-row"><label style={{minWidth:0,fontSize:11}}>classify</label><select className="am-select"><option>haiku-4.5</option></select></div>
            <div className="am-input-row"><label style={{minWidth:0,fontSize:11}}>match</label><select className="am-select"><option>haiku-4.5</option></select></div>
          </div>
        </div>

        <div className="am-step">
          <div className="am-step-h">
            <div className="am-step-num">7</div>
            <div className="am-step-title">Уведомления</div>
          </div>
          <div style={{display:'flex', gap:14, marginBottom:12}}>
            <label className="am-check"><input type="checkbox" defaultChecked/> Telegram</label>
            <label className="am-check" style={{color:'var(--text-muted)'}}><input type="checkbox" disabled/> Max <span style={{fontSize:10}}>(скоро)</span></label>
          </div>
          <div style={{display:'grid', gridTemplateColumns:'repeat(2, 1fr)', gap:10, fontSize:12}}>
            <label className="am-check"><input type="checkbox" defaultChecked/> new_listing</label>
            <div style={{display:'flex',gap:8,alignItems:'center'}}><label className="am-check"><input type="checkbox" defaultChecked/> price_drop</label><span style={{color:'var(--text-muted)'}}>≥</span><input className="am-input" style={{width:60}} defaultValue="10"/><span style={{color:'var(--text-muted)'}}>%</span></div>
            <div style={{display:'flex',gap:8,alignItems:'center'}}><label className="am-check"><input type="checkbox" defaultChecked/> market_trend</label><span style={{color:'var(--text-muted)'}}>≥</span><input className="am-input" style={{width:60}} defaultValue="5"/><span style={{color:'var(--text-muted)'}}>%</span></div>
            <div style={{display:'flex',gap:8,alignItems:'center'}}><label className="am-check"><input type="checkbox" defaultChecked/> historical_low</label><span style={{color:'var(--text-muted)'}}>окно</span><input className="am-input" style={{width:60}} defaultValue="30"/><span style={{color:'var(--text-muted)'}}>д</span></div>
            <label className="am-check"><input type="checkbox"/> supply_surge</label>
            <label className="am-check"><input type="checkbox"/> condition_mix_change</label>
          </div>
        </div>

        <div style={{display:'flex', justifyContent:'flex-end', gap:10}}>
          <button className="am-btn">Отмена</button>
          <button className="am-btn am-btn-primary">Сохранить и запустить</button>
        </div>
      </div>
    </div>
  );
}

window.ScreenProfileCreate = ScreenProfileCreate;

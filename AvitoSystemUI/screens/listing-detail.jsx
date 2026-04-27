/* global React, TopBar, Sidebar, ConditionChip, AM_FMT, AM_DATA, Chart */

function ScreenListingDetail({ theme }) {
  const item = AM_DATA.listings[5]; // 256GB pacific blue, price drop -7.6%
  const chartRef = React.useRef(null);
  const useEffect = React.useEffect;

  useEffect(() => {
    if (!window.Chart || !chartRef.current) return;
    const data = AM_DATA.history.slice(-21).map(h => ({ x: h.d, y: h.median }));
    // synthetic single-listing price track
    const lp = [16100, 16100, 15800, 15800, 15500, 15200, 15200, 15000, 14800, 14800, 14500, 14500, 14500, 14400, 14400, 14400, 14400, 14400, 14000, 14000, 13400];
    const labels = data.map(d => d.x);
    const ctx = chartRef.current.getContext('2d');
    const chart = new Chart(ctx, {
      type: 'line',
      data: {
        labels,
        datasets: [
          {
            label: 'Цена этого лота',
            data: lp,
            borderColor: '#97CF26',
            backgroundColor: 'rgba(151, 207, 38, 0.1)',
            fill: true,
            tension: 0.25,
            pointRadius: 0,
            pointHoverRadius: 5,
            borderWidth: 2.5,
          },
          {
            label: 'Медиана рынка',
            data: data.map(d => d.y),
            borderColor: '#8C95A1',
            backgroundColor: 'transparent',
            borderDash: [4, 3],
            tension: 0.25,
            pointRadius: 0,
            borderWidth: 1.5,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { display: false } },
        scales: {
          x: { grid: { color: 'rgba(225,228,232,0.6)' }, ticks: { color: '#5C6878', font: { size: 11 } } },
          y: { grid: { color: 'rgba(225,228,232,0.6)' }, ticks: { color: '#5C6878', font: { size: 11 }, callback: v => (v/1000) + 'K' } },
        },
      },
    });
    return () => chart.destroy();
  }, []);

  return (
    <div className={`am-screen theme-${theme}`}>
      <TopBar theme={theme} />
      <Sidebar active="listings" />
      <div className="am-content scroll-y">
        <div className="am-bcrumb">
          <span>Лоты</span>
          <span>›</span>
          <span>iPhone 12 Pro Max до 13.5K</span>
          <span>›</span>
          <span className="cur">#{item.id}</span>
        </div>

        <div className="am-page-h">
          <div>
            <h1 style={{margin:0}}>iPhone 12 Pro Max 256GB pacific blue</h1>
            <div style={{display:'flex',gap:8,marginTop:8,alignItems:'center',flexWrap:'wrap'}}>
              <ConditionChip value={item.condition} theme={theme}/>
              <span className="am-pill" style={{background:'#FFE5E5',color:'#C92533'}}>● В alert-зоне</span>
              <span style={{fontSize:13,color:'var(--text-muted)'}}>#{item.id}</span>
              <span style={{fontSize:13,color:'var(--text-muted)'}}>· замечено 25.04 02:18</span>
            </div>
          </div>
          <div style={{display:'flex',gap:8}}>
            <button className="am-btn am-btn-sm">Скрыть</button>
            <button className="am-btn am-btn-sm">↗ На Avito</button>
            <button className="am-btn am-btn-primary am-btn-sm">💬 Написать</button>
          </div>
        </div>

        <div className="am-detail-grid">
          {/* LEFT: gallery + chat preview */}
          <div className="am-detail-left">
            <div className="am-gallery">
              <div className="am-gallery-main" style={{background: item.color}}>
                <svg width="180" height="280" viewBox="0 0 36 56" fill="none">
                  <rect x="2" y="2" width="32" height="52" rx="5" stroke="rgba(255,255,255,0.45)" strokeWidth="1.5"/>
                  <rect x="5" y="6" width="26" height="38" rx="2" fill="rgba(255,255,255,0.15)"/>
                  <circle cx="18" cy="49" r="1.5" fill="rgba(255,255,255,0.35)"/>
                  <rect x="10" y="3.5" width="8" height="2" rx="1" fill="rgba(0,0,0,0.4)"/>
                  <rect x="22" y="9" width="4" height="4" rx="1" fill="rgba(255,255,255,0.6)"/>
                </svg>
                <div className="am-gallery-counter">1 / 6</div>
              </div>
              <div className="am-gallery-thumbs">
                {[item.color, '#3F4855', '#1F3A6E', '#3D5A75', '#C8C9CD', '#E8D7B5'].map((c, i) => (
                  <div key={i} className={`am-gallery-thumb ${i === 0 ? 'active' : ''}`} style={{background: c}}>
                    <svg width="32" height="48" viewBox="0 0 36 56" fill="none">
                      <rect x="2" y="2" width="32" height="52" rx="5" stroke="rgba(255,255,255,0.4)" strokeWidth="1.5"/>
                      <rect x="5" y="6" width="26" height="38" rx="2" fill="rgba(255,255,255,0.12)"/>
                    </svg>
                  </div>
                ))}
              </div>
            </div>

            <div className="am-set-card" style={{marginTop:16}}>
              <div className="am-set-card-title" style={{marginBottom:12}}>Описание (с Avito)</div>
              <div style={{fontSize:14,color:'var(--text-secondary)',lineHeight:1.6}}>
                Продаю iPhone 12 Pro Max 256GB Pacific Blue. Состояние отличное, всё работает идеально, аккумулятор 87%. Комплект: коробка, кабель, адаптер. Без торга по телефону, торг при осмотре. Москва, метро Сокольники, могу подъехать.
              </div>
              <div className="am-llm-box">
                <div className="am-llm-h">
                  <span style={{fontSize:13,fontWeight:600}}>🤖 LLM-классификация</span>
                  <span className="am-pill" style={{background:'var(--brand-soft)',color:'#4d6b14',fontSize:11}}>Haiku 4.5 · $0.0002</span>
                </div>
                <div className="am-llm-grid">
                  <div><span className="lbl">Состояние</span><span className="v">working (98%)</span></div>
                  <div><span className="lbl">Тип продавца</span><span className="v">частник</span></div>
                  <div><span className="lbl">Комплектация</span><span className="v">полная</span></div>
                  <div><span className="lbl">Битые пиксели</span><span className="v">не упомянуты</span></div>
                  <div><span className="lbl">Аккумулятор</span><span className="v">87% (явно)</span></div>
                  <div><span className="lbl">Торг</span><span className="v">только при осмотре</span></div>
                </div>
              </div>
            </div>
          </div>

          {/* RIGHT: price + chart + seller + actions */}
          <div className="am-detail-right">
            <div className="am-set-card am-detail-price">
              <div className="am-detail-price-row">
                <div>
                  <div className="am-detail-price-current">13 400 ₽</div>
                  <div className="am-detail-price-delta">
                    <span className="dn">▼ 7.6%</span>
                    <span style={{color:'var(--text-muted)'}}>было 14 500 ₽ · 21.04</span>
                  </div>
                </div>
                <div className="am-detail-zone">
                  <div className="lbl">Зона</div>
                  <div className="v">ALERT</div>
                  <div className="r">11.0K – 13.5K</div>
                </div>
              </div>
              <div className="am-detail-vs">
                <div><span className="lbl">vs медиана</span><span className="v dn">−2.7% дешевле</span></div>
                <div><span className="lbl">vs мин 30д</span><span className="v">+5.3% выше</span></div>
                <div><span className="lbl">vs alert-max</span><span className="v dn">−0.7% ниже</span></div>
              </div>
            </div>

            <div className="am-set-card">
              <div style={{display:'flex',justifyContent:'space-between',alignItems:'baseline',marginBottom:14}}>
                <div className="am-set-card-title">История цены · 21 день</div>
                <div style={{fontSize:12,color:'var(--text-muted)'}}>3 изменения</div>
              </div>
              <div style={{height:200, position:'relative'}}>
                <canvas ref={chartRef}></canvas>
              </div>
              <div className="am-detail-events">
                <div className="ev"><span className="dt">21.04</span><span className="dn">−6.9%</span><span>16 100 → 15 000 ₽</span></div>
                <div className="ev"><span className="dt">23.04</span><span className="dn">−3.3%</span><span>15 000 → 14 500 ₽</span></div>
                <div className="ev"><span className="dt">25.04</span><span className="dn strong">−7.6%</span><span>14 500 → 13 400 ₽ <span className="am-pill" style={{background:'var(--brand-soft)',color:'#4d6b14',fontSize:10,padding:'2px 6px',marginLeft:4}}>в alert</span></span></div>
              </div>
            </div>

            <div className="am-set-card">
              <div className="am-seller-row">
                <div style={{width:48,height:48,borderRadius:'50%',background:'#1989C5',display:'grid',placeItems:'center',color:'#fff',fontWeight:600}}>TP</div>
                <div style={{flex:1,minWidth:0}}>
                  <div style={{fontWeight:600}}>Telecom Plus</div>
                  <div style={{fontSize:13,color:'var(--text-muted)'}}>Магазин · на Avito с 2019 · 124 объявления</div>
                </div>
                <div style={{textAlign:'right'}}>
                  <div style={{fontSize:18,fontWeight:600,color:'var(--positive)'}}>4.9 ★</div>
                  <div style={{fontSize:12,color:'var(--text-muted)'}}>847 отзывов</div>
                </div>
              </div>
              <div className="am-seller-stats">
                <div><span className="lbl">Активных лотов</span><span className="v">12 iPhone</span></div>
                <div><span className="lbl">Средняя цена</span><span className="v">14 200 ₽</span></div>
                <div><span className="lbl">Время ответа</span><span className="v">~ 8 мин</span></div>
                <div><span className="lbl">Регион</span><span className="v">Москва</span></div>
              </div>
            </div>

            <div className="am-set-card">
              <div className="am-set-card-title" style={{marginBottom:12}}>Быстрые действия</div>
              <div style={{display:'grid',gridTemplateColumns:'1fr 1fr',gap:8}}>
                <button className="am-btn">📌 Закрепить в топе</button>
                <button className="am-btn">🔕 Скрыть продавца</button>
                <button className="am-btn">📋 Скопировать ссылку</button>
                <button className="am-btn">⚠ Жалоба на лот</button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

window.ScreenListingDetail = ScreenListingDetail;

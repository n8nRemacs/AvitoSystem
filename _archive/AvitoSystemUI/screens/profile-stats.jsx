/* global React, TopBar, Sidebar, Kpi, MarketEventRow, DualPriceRange, AM_DATA, Chart */

function ScreenProfileStats({ theme }) {
  const useEffect = React.useEffect;
  const useRef = React.useRef;

  const D = AM_DATA;
  const lineRef = useRef(null);
  const histRef = useRef(null);
  const donutRef = useRef(null);

  useEffect(() => {
    if (!window.Chart) return;
    const isTrader = theme === 'trader';
    const grid = isTrader ? 'rgba(48,54,61,0.5)' : 'rgba(225,228,232,0.6)';
    const text = isTrader ? '#8B949E' : '#5C6878';
    const lineColor = isTrader ? '#58A6FF' : '#97CF26';
    const fill = isTrader ? 'rgba(88,166,255,0.13)' : 'rgba(151,207,38,0.16)';
    const fontFamily = isTrader ? "'JetBrains Mono', monospace" : "'Inter', sans-serif";

    const charts = [];
    // Line chart
    if (lineRef.current) {
      const ctx = lineRef.current.getContext('2d');
      charts.push(new Chart(ctx, {
        type: 'line',
        data: {
          labels: D.history.map(h => h.d),
          datasets: [
            {
              label: 'Median (clean)',
              data: D.history.map(h => h.median),
              borderColor: lineColor,
              backgroundColor: fill,
              borderWidth: isTrader ? 1.5 : 2,
              fill: true,
              tension: isTrader ? 0 : 0.3,
              pointRadius: isTrader ? 0 : 2.5,
              pointHoverRadius: 5,
              pointBackgroundColor: lineColor,
            }
          ]
        },
        options: {
          responsive: true, maintainAspectRatio: false,
          plugins: {
            legend: { display: false },
            // Alert band annotation drawn via custom plugin
          },
          scales: {
            y: {
              grid: { color: grid },
              ticks: { color: text, font: { family: fontFamily, size: 10 }, callback: (v) => (v/1000).toFixed(0)+'K' },
              min: 7000, max: 19000,
            },
            x: {
              grid: { color: grid, display: false },
              ticks: { color: text, font: { family: fontFamily, size: 10 }, maxTicksLimit: 8 },
            }
          }
        },
        plugins: [{
          id: 'alertBand',
          beforeDatasetsDraw(chart) {
            const {ctx, chartArea, scales} = chart;
            const yMin = scales.y.getPixelForValue(11000);
            const yMax = scales.y.getPixelForValue(13500);
            ctx.save();
            ctx.fillStyle = isTrader ? 'rgba(63,185,80,0.08)' : 'rgba(151,207,38,0.18)';
            ctx.fillRect(chartArea.left, yMax, chartArea.right - chartArea.left, yMin - yMax);
            ctx.strokeStyle = isTrader ? 'rgba(63,185,80,0.5)' : 'rgba(151,207,38,0.7)';
            ctx.setLineDash([4,4]);
            ctx.lineWidth = 1;
            ctx.beginPath(); ctx.moveTo(chartArea.left, yMin); ctx.lineTo(chartArea.right, yMin); ctx.stroke();
            ctx.beginPath(); ctx.moveTo(chartArea.left, yMax); ctx.lineTo(chartArea.right, yMax); ctx.stroke();
            ctx.setLineDash([]);
            ctx.fillStyle = isTrader ? '#3FB950' : '#5A8C00';
            ctx.font = `10px ${fontFamily}`;
            ctx.fillText('alert max 13.5K', chartArea.right - 90, yMax - 4);
            ctx.fillText('alert min 11.0K', chartArea.right - 90, yMin + 12);
            ctx.restore();
          }
        }]
      }));
    }

    // Histogram
    if (histRef.current) {
      const buckets = [
        { label: '8K',  working: 0, broken: 0, parts: 1 },
        { label: '9K',  working: 0, broken: 0, parts: 0, icloud: 1 },
        { label: '10K', working: 0, broken: 0, parts: 0 },
        { label: '11K', working: 0, broken: 1, parts: 0 },
        { label: '12K', working: 1, broken: 0, parts: 0, icloud: 1 },
        { label: '13K', working: 4, broken: 1, parts: 0 },
        { label: '14K', working: 1, broken: 0, parts: 0 },
        { label: '15K', working: 0, broken: 0, parts: 0 },
        { label: '16K', working: 1, broken: 0, parts: 0 },
      ];
      const ctx = histRef.current.getContext('2d');
      charts.push(new Chart(ctx, {
        type: 'bar',
        data: {
          labels: buckets.map(b => b.label),
          datasets: [
            { label: 'working', data: buckets.map(b => b.working || 0), backgroundColor: isTrader ? '#3FB950' : '#97CF26', stack: 's' },
            { label: 'broken',  data: buckets.map(b => b.broken  || 0), backgroundColor: isTrader ? '#F85149' : '#DC3545', stack: 's' },
            { label: 'iCloud',  data: buckets.map(b => b.icloud  || 0), backgroundColor: isTrader ? '#D29922' : '#FFB900', stack: 's' },
            { label: 'parts',   data: buckets.map(b => b.parts   || 0), backgroundColor: isTrader ? '#6E7681' : '#8C95A1', stack: 's' },
          ],
        },
        options: {
          responsive: true, maintainAspectRatio: false,
          plugins: { legend: { display: true, labels: { color: text, font: { family: fontFamily, size: 10 } } } },
          scales: {
            x: { stacked: true, grid: { display: false }, ticks: { color: text, font: { family: fontFamily, size: 10 } } },
            y: { stacked: true, grid: { color: grid }, ticks: { color: text, font: { family: fontFamily, size: 10 }, stepSize: 1 }, min: 0, max: 6 },
          }
        }
      }));
    }

    // Donut
    if (donutRef.current) {
      const ctx = donutRef.current.getContext('2d');
      charts.push(new Chart(ctx, {
        type: 'doughnut',
        data: {
          labels: ['working','iCloud-блок','разбит экран','поломка','на запчасти'],
          datasets: [{
            data: [5,3,2,1,1],
            backgroundColor: isTrader
              ? ['#3FB950','#D29922','#F85149','#BC8CFF','#6E7681']
              : ['#97CF26','#FFB900','#DC3545','#9966CC','#8C95A1'],
            borderWidth: 0,
          }]
        },
        options: {
          responsive: true, maintainAspectRatio: false, cutout: '65%',
          plugins: { legend: { position: 'right', labels: { color: text, font: { family: fontFamily, size: 11 } } } }
        }
      }));
    }

    return () => charts.forEach(c => c.destroy());
  }, [theme]);

  return (
    <div className={`am-screen theme-${theme}`}>
      <TopBar theme={theme}/>
      <Sidebar active="profiles"/>
      <div className="am-content scroll-y">
        <div className="am-page-h">
          <div>
            <div style={{fontSize:11,color:'var(--text-muted)',marginBottom:4}}>← К списку профилей</div>
            <h1 style={{display:'flex',alignItems:'center',gap:10}}>
              <span className="am-dot on"></span>
              {D.profile.name}
            </h1>
            <div style={{fontSize:12,color:'var(--text-secondary)',marginTop:4}}>
              Apple / iPhone 12 Pro Max / Москва · 5 мин · 09–23 · последний прогон 25.04 10:34
            </div>
          </div>
          <div style={{display:'flex',gap:8}}>
            <button className="am-btn am-btn-sm">⏸ Пауза</button>
            <button className="am-btn am-btn-sm">⚙ Редакт.</button>
            <button className="am-btn am-btn-primary am-btn-sm">📦 Посмотреть лоты (12)</button>
          </div>
        </div>

        <div className="am-kpi-row">
          <Kpi label="Лотов 24ч" value="12" delta="+4 новых" deltaCls="pos"/>
          <Kpi label="В alert-зоне" value="7" delta="working: 5"/>
          <Kpi label="Медиана (clean)" value="13 050 ₽" delta="▼ 9.6% / 30д" deltaCls="neg"/>
          <Kpi label="Working share" value="41.7%" delta="+5% / неделя" deltaCls="pos"/>
        </div>

        <div style={{display:'grid', gridTemplateColumns:'1.4fr 1fr', gap:14}}>
          <div className="am-card">
            <div className="am-card-h">
              <h3>Динамика цены — 30 дней</h3>
              <div className="am-chips-row">
                <button className="am-fchip active">Median clean</button>
                <button className="am-fchip">Median raw</button>
                <button className="am-fchip">Min</button>
                <button className="am-fchip">Max</button>
              </div>
            </div>
            <div style={{height:240, position:'relative'}}>
              <canvas ref={lineRef}></canvas>
            </div>
            <div style={{fontSize:11,color:'var(--text-muted)',marginTop:8}}>
              Пунктирная зона = alert-вилка · Текущая median: <span style={{color:'var(--text-primary)',fontWeight:600}} className="mono">13 050 ₽</span> <span style={{color:'var(--negative)'}} className="mono">▼ 9.6%</span>
            </div>
          </div>

          <div className="am-card">
            <div className="am-card-h"><h3>Состав по состояниям</h3></div>
            <div style={{height:240, position:'relative'}}>
              <canvas ref={donutRef}></canvas>
            </div>
            <div style={{fontSize:11,color:'var(--text-muted)',marginTop:8,textAlign:'center'}}>
              Из 12 лотов · working = 5 (41.7%)
            </div>
          </div>
        </div>

        <div style={{display:'grid', gridTemplateColumns:'1fr 1fr', gap:14, marginTop:14}}>
          <div className="am-card">
            <div className="am-card-h">
              <h3>Цены лотов сейчас (n=12)</h3>
            </div>
            <div style={{height:200, position:'relative'}}>
              <canvas ref={histRef}></canvas>
            </div>
            <div style={{fontSize:11,color:'var(--text-muted)',marginTop:8}}>
              Зелёная подложка под X-осью = alert-вилка 11–13.5K ₽
            </div>
          </div>

          <div className="am-card">
            <div className="am-card-h">
              <h3>События рынка — 7 дней</h3>
              <span className="am-link">→ Все</span>
            </div>
            <div style={{maxHeight:200, overflowY:'auto'}}>
              {D.events.map((e,i) => <MarketEventRow key={i} event={e} theme={theme}/>)}
            </div>
          </div>
        </div>

        {/* Auto-recommend alert range */}
        <div className="am-card" style={{marginTop:14, background: theme==='trader' ? 'color-mix(in srgb, var(--accent) 6%, var(--surface))' : 'var(--brand-soft)', borderColor: 'var(--accent)'}}>
          <div style={{display:'flex',alignItems:'center',justifyContent:'space-between',gap:14}}>
            <div style={{flex:1}}>
              <div style={{fontSize:13,fontWeight:600,marginBottom:4}}>💡 Авто-рекомендация alert-вилки</div>
              <div style={{fontSize:12, color:'var(--text-secondary)'}}>
                Текущая: <span className="mono" style={{color:'var(--text-primary)'}}>11 000 – 13 500 ₽</span>
                &nbsp;&nbsp;·&nbsp;&nbsp;Рекомендую (по медиане 13 050 и p25/p75):
                &nbsp;<span className="mono" style={{color: theme==='trader' ? 'var(--accent)' : 'var(--brand-hover)', fontWeight:600}}>10 500 – 13 000 ₽</span>
              </div>
            </div>
            <div style={{display:'flex',gap:8}}>
              <button className="am-btn am-btn-sm">Игнорировать</button>
              <button className="am-btn am-btn-primary am-btn-sm">Применить</button>
            </div>
          </div>
        </div>

        <div className="am-state-note" style={{marginTop:14}}>
          <span className="lbl">Empty</span>«Запусти первый прогон чтобы увидеть статистику».
          &nbsp;&nbsp;<span className="lbl">Stale</span>«Данные устарели — последний прогон 18 минут назад» (серый баннер).
        </div>
      </div>
    </div>
  );
}

window.ScreenProfileStats = ScreenProfileStats;

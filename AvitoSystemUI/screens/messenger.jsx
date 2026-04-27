/* global React */

// Messenger preview — TG (left) + Max (right). Both themes share this screen
// but the surrounding artboard chrome flips with parent theme.

function ScreenMessenger({ theme }) {
  return (
    <div className={`theme-${theme}`} style={{width:'100%', height:'100%', background:'var(--bg)', padding:24, display:'grid', gridTemplateColumns:'1fr 1fr', gap:18}}>
      {/* TG */}
      <div style={{display:'flex',flexDirection:'column'}}>
        <div style={{fontSize:11,color:'var(--text-muted)',textTransform:'uppercase',letterSpacing:'0.1em',marginBottom:8,fontFamily:theme==='trader'?'var(--font-mono)':'inherit'}}>Telegram · @avito_monitor_bot</div>
        <div className="am-msg-frame" style={{flex:1, borderRadius:12, overflow:'hidden'}}>
          <div className="am-msg-header" style={{background:'#2A3949', color:'#fff', borderBottom:'1px solid rgba(255,255,255,0.05)'}}>
            <div style={{width:32,height:32,borderRadius:'50%',background:'#58A6FF',display:'grid',placeItems:'center',fontWeight:700, color:'#0E1116'}}>AM</div>
            <div>
              <div>Avito Monitor</div>
              <div style={{fontSize:11,fontWeight:400,color:'rgba(255,255,255,0.5)'}}>bot · online</div>
            </div>
          </div>
          <div className="am-msg-body">
            <TGBubble title="🔻 Цена упала на 7.6%" lines={[
              ['iPhone 12 Pro Max 256GB Pacific Blue'],
              ['Studio M (компания)'],
              [{strike:'14 500 ₽'}, ' → ', {b:'13 400 ₽'}],
              [],
              [{m:'Профиль:'}, ' iPhone 12 Pro Max до 13.5K'],
              [{m:'Состояние:'}, ' рабочий ✅'],
              [{m:'LLM:'}, ' соответствует (акк. 88%, без сколов)'],
            ]} actions={['Открыть на Avito','Скрыть продавца','Не показывать']} time="10:34"/>

            <TGBubble title="📉 Историческое дно" lines={[
              ['iPhone 12 Pro Max 128GB Gold'],
              ['Артём (частник)'],
              [{b:'12 800 ₽'}, ' — минимум за 30 дней'],
              [],
              [{m:'Предыдущий мин:'}, ' 13 080 ₽ (10.04)'],
              [{m:'Состояние:'}, ' рабочий ✅'],
            ]} actions={['Открыть на Avito','✓ Просмотрено','Скрыть']} time="07:32"/>

            <TGBubble title="📊 Тренд рынка: −9.6% / месяц" lines={[
              [{b:'iPhone 12 Pro Max'}],
              [{m:'Медиана 26.03:'}, ' 14 050 ₽'],
              [{m:'Медиана 25.04:'}, ' 13 050 ₽'],
              [],
              [{m:'Рекомендуемая alert-вилка:'}],
              [{m:'текущая:'}, ' 11 000 – 13 500 ₽'],
              [{m:'рекомендую:'}, ' ', {b:'10 500 – 13 000 ₽'}],
            ]} actions={['Применить','Игнорировать']} time="09:15"/>

            <TGBubble title="📦 Всплеск предложения +35%" lines={[
              [{b:'iPhone 12 Pro Max'}],
              [{m:'Активных:'}, ' 28 → 35 за неделю'],
              [{m:'Появилось:'}, ' 18 · ', {m:'скрылось:'}, ' 11'],
              [],
              ['Возможный сигнал к снижению цен.'],
            ]} actions={['Открыть Stats','Игнорировать']} time="11:30"/>
          </div>
        </div>
      </div>

      {/* Max */}
      <div style={{display:'flex',flexDirection:'column'}}>
        <div style={{fontSize:11,color:'var(--text-muted)',textTransform:'uppercase',letterSpacing:'0.1em',marginBottom:8,fontFamily:theme==='trader'?'var(--font-mono)':'inherit'}}>Max · Avito Monitor <span style={{background:'var(--surface-elev)',padding:'1px 6px',borderRadius:4,marginLeft:6}}>V2</span></div>
        <div className="am-msg-frame" style={{flex:1, borderRadius:18, overflow:'hidden', background:'#fff'}}>
          <div className="am-msg-header" style={{background:'linear-gradient(180deg, #1989C5 0%, #1474AB 100%)', color:'#fff', padding:'14px 18px', borderBottom: 'none'}}>
            <div style={{width:36,height:36,borderRadius:18,background:'rgba(255,255,255,0.2)',display:'grid',placeItems:'center',fontWeight:700}}>AM</div>
            <div>
              <div style={{fontSize:15}}>Avito Monitor</div>
              <div style={{fontSize:11,fontWeight:400,color:'rgba(255,255,255,0.7)'}}>в сети</div>
            </div>
          </div>
          <div className="am-msg-body max-body">
            <MaxBubble title="🔻 Цена упала на 7.6%" lines={[
              [{b:'iPhone 12 Pro Max 256GB Pacific Blue'}],
              ['Studio M · компания'],
              [{strike:'14 500 ₽'}, ' → ', {b:'13 400 ₽'}],
              [],
              [{m:'Состояние:'}, ' рабочий ✅ · ', {m:'LLM match:'}, ' 88%'],
            ]} actions={['Открыть на Avito','Скрыть','Не показывать']} time="10:34"/>

            <MaxBubble title="📉 Историческое дно" lines={[
              [{b:'iPhone 12 Pro Max 128GB Gold'}],
              ['Артём · частник'],
              [{b:'12 800 ₽'}, ' — минимум за 30 дней'],
              [],
              [{m:'Предыдущий мин:'}, ' 13 080 ₽ (10.04)'],
            ]} actions={['Открыть','Просмотрено']} time="07:32"/>

            <MaxBubble title="📊 Тренд −9.6% / месяц" lines={[
              [{m:'Медиана:'}, ' 14 050 → 13 050 ₽'],
              [{m:'Рекомендую вилку:'}, ' ', {b:'10 500 – 13 000 ₽'}],
            ]} actions={['Применить','Игнорировать']} time="09:15"/>
          </div>
        </div>
        <div style={{fontSize:10,color:'var(--text-muted)',textAlign:'right',marginTop:6,fontStyle:'italic'}}>
          Максимально близкий стиль; точная Max-кнопка/шрифт — после релиза V2.
        </div>
      </div>
    </div>
  );
}

function renderLine(line) {
  if (!line || !line.length) return <div style={{height:6}}></div>;
  return line.map((part, i) => {
    if (typeof part === 'string') return <span key={i}>{part}</span>;
    if (part.b) return <b key={i}>{part.b}</b>;
    if (part.m) return <span key={i} style={{color:'rgba(255,255,255,0.5)'}}>{part.m}</span>;
    if (part.strike) return <span key={i} style={{textDecoration:'line-through',color:'rgba(255,255,255,0.45)'}}>{part.strike}</span>;
    return null;
  });
}

function renderLineMax(line) {
  if (!line || !line.length) return <div style={{height:6}}></div>;
  return line.map((part, i) => {
    if (typeof part === 'string') return <span key={i}>{part}</span>;
    if (part.b) return <b key={i}>{part.b}</b>;
    if (part.m) return <span key={i} style={{color:'#8C95A1'}}>{part.m}</span>;
    if (part.strike) return <span key={i} style={{textDecoration:'line-through',color:'#8C95A1'}}>{part.strike}</span>;
    return null;
  });
}

function TGBubble({ title, lines, actions, time }) {
  return (
    <div className="am-msg-bubble">
      <div className="am-msg-title">{title}</div>
      <div style={{display:'flex',flexDirection:'column',gap:2,fontSize:12.5,lineHeight:1.5}}>
        {lines.map((l,i) => <div key={i}>{renderLine(l)}</div>)}
      </div>
      <div className="am-msg-actions">
        {actions.map((a,i) => <span key={i} className="am-msg-action">{a}</span>)}
      </div>
      <div className="am-msg-meta">{time}</div>
    </div>
  );
}

function MaxBubble({ title, lines, actions, time }) {
  return (
    <div className="am-msg-bubble max">
      <div className="am-msg-title" style={{color:'#1B1F26'}}>{title}</div>
      <div style={{display:'flex',flexDirection:'column',gap:2,fontSize:13.5,lineHeight:1.5,color:'#1B1F26'}}>
        {lines.map((l,i) => <div key={i}>{renderLineMax(l)}</div>)}
      </div>
      <div className="am-msg-actions">
        {actions.map((a,i) => <span key={i} className="am-msg-action max">{a}</span>)}
      </div>
      <div className="am-msg-meta">{time}</div>
    </div>
  );
}

window.ScreenMessenger = ScreenMessenger;

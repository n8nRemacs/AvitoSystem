/* global React, DesignCanvas, DCSection, DCArtboard, TweaksPanel, useTweaks, TweakToggle */

const TWEAK_DEFAULTS = /*EDITMODE-BEGIN*/{
  "showStateNotes": true,
  "denseListings": false
}/*EDITMODE-END*/;

function App() {
  const [tweaks, setTweak] = useTweaks(TWEAK_DEFAULTS);

  React.useEffect(() => {
    const sheet = document.getElementById('state-note-toggle') || (() => {
      const s = document.createElement('style');
      s.id = 'state-note-toggle';
      document.head.appendChild(s);
      return s;
    })();
    sheet.textContent = tweaks.showStateNotes ? '' : '.am-state-note { display: none !important; }';
  }, [tweaks.showStateNotes]);

  return (
    <>
      <DesignCanvas defaultZoom={0.45}>
        <DCSection id="avito" title="Avito Monitor · Light & Friendly" subtitle="Off-white фон, зелёный CTA в духе Avito, мягкие pill-чипы. Desktop-only, аудитория из одного человека.">
          <DCArtboard id="a-dashboard" label="1 · Дашборд" width={1440} height={1080}>
            <ScreenDashboard theme="avito"/>
          </DCArtboard>
          <DCArtboard id="a-create" label="2 · Создание профиля" width={1440} height={1900}>
            <ScreenProfileCreate theme="avito"/>
          </DCArtboard>
          <DCArtboard id="a-stats" label="3 · Статистика профиля" width={1440} height={1280}>
            <ScreenProfileStats theme="avito"/>
          </DCArtboard>
          <DCArtboard id="a-listings" label="4 · Лента лотов" width={1440} height={1700}>
            <ScreenListings theme="avito"/>
          </DCArtboard>
          <DCArtboard id="a-msg" label="5 · Telegram-уведомление" width={900} height={1100}>
            <ScreenMessenger theme="avito"/>
          </DCArtboard>
          <DCArtboard id="a-detail" label="6 · Детали лота" width={1440} height={1500}>
            <ScreenListingDetail theme="avito"/>
          </DCArtboard>
          <DCArtboard id="a-prices" label="7 · Цены — кросс-обзор" width={1440} height={1300}>
            <ScreenPrices theme="avito"/>
          </DCArtboard>
          <DCArtboard id="a-logs" label="8 · Логи" width={1440} height={1500}>
            <ScreenLogs theme="avito"/>
          </DCArtboard>
          <DCArtboard id="a-settings" label="9 · Настройки" width={1440} height={1400}>
            <ScreenSettings theme="avito"/>
          </DCArtboard>
        </DCSection>
      </DesignCanvas>

      <TweaksPanel title="Tweaks">
        <div style={{fontSize:11,color:'#666',marginBottom:8,lineHeight:1.5,padding:'0 2px'}}>
          Клик по подписи артборда — focus-mode. Drag — переупорядочить.
        </div>
        <TweakToggle
          label="Врезки состояний"
          value={tweaks.showStateNotes}
          onChange={(v) => setTweak('showStateNotes', v)}
        />
      </TweaksPanel>
    </>
  );
}

ReactDOM.createRoot(document.getElementById('root')).render(<App/>);

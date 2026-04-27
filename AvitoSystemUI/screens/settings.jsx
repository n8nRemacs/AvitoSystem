/* global React, TopBar, Sidebar, AM_FMT */

function ScreenSettings({ theme }) {
  const [tab, setTab] = React.useState('integrations');
  const [pollInterval, setPollInterval] = React.useState(5);
  const [tgEnabled, setTgEnabled] = React.useState(true);
  const [emailEnabled, setEmailEnabled] = React.useState(false);
  const [llmModel, setLlmModel] = React.useState('claude-haiku-4-5');
  const [showApiKey, setShowApiKey] = React.useState(false);

  const tabs = [
    { id: 'integrations', label: 'Интеграции', icon: '🔌' },
    { id: 'notifications', label: 'Уведомления', icon: '🔔' },
    { id: 'parsing', label: 'Парсинг', icon: '⚙️' },
    { id: 'billing', label: 'Расходы', icon: '💳' },
    { id: 'account', label: 'Аккаунт', icon: '👤' },
    { id: 'danger', label: 'Опасная зона', icon: '⚠️' },
  ];

  return (
    <div className={`am-screen theme-${theme}`}>
      <TopBar theme={theme} />
      <Sidebar active="settings" />
      <div className="am-content scroll-y">
        <div className="am-page-h">
          <h1>Настройки</h1>
          <button className="am-btn am-btn-primary am-btn-sm">Сохранить изменения</button>
        </div>

        {/* Settings nav tabs */}
        <div className="am-settings-tabs">
          {tabs.map(t => (
            <button
              key={t.id}
              className={`am-settings-tab ${tab === t.id ? 'active' : ''} ${t.id === 'danger' ? 'danger' : ''}`}
              onClick={() => setTab(t.id)}
            >
              <span style={{fontSize:14}}>{t.icon}</span>
              <span>{t.label}</span>
            </button>
          ))}
        </div>

        {/* INTEGRATIONS */}
        {tab === 'integrations' && (
          <div className="am-settings-pane">
            <div className="am-set-card">
              <div className="am-set-card-h">
                <div>
                  <div className="am-set-card-title">Anthropic API</div>
                  <div className="am-set-card-sub">LLM для классификации лотов и матчинга</div>
                </div>
                <span className="am-pill am-pill-ok">● Подключено</span>
              </div>

              <div className="am-set-row">
                <label className="am-set-label">API-ключ</label>
                <div style={{display:'flex',gap:8,alignItems:'center'}}>
                  <input
                    className="am-input"
                    type={showApiKey ? 'text' : 'password'}
                    defaultValue="sk-ant-api03-x7K9mP2nQ8vR4sT6uW9xY1zA3bC5dE7fG9hJ"
                    style={{flex:1, fontFamily:'var(--font-mono)', fontSize:13}}
                  />
                  <button className="am-btn am-btn-sm" onClick={() => setShowApiKey(!showApiKey)}>
                    {showApiKey ? '🙈 Скрыть' : '👁 Показать'}
                  </button>
                  <button className="am-btn am-btn-sm">Заменить</button>
                </div>
                <div className="am-set-hint">Создать ключ → console.anthropic.com</div>
              </div>

              <div className="am-set-row">
                <label className="am-set-label">Модель</label>
                <div style={{display:'grid',gridTemplateColumns:'repeat(3,1fr)',gap:8}}>
                  {[
                    {v:'claude-haiku-4-5', name:'Haiku 4.5', cost:'$0.25/1M', tag:'дёшево'},
                    {v:'claude-sonnet-4-5', name:'Sonnet 4.5', cost:'$3/1M', tag:'рекоменд.'},
                    {v:'claude-opus-4', name:'Opus 4', cost:'$15/1M', tag:'дорого'},
                  ].map(m => (
                    <div
                      key={m.v}
                      className={`am-radio-card ${llmModel === m.v ? 'active' : ''}`}
                      onClick={() => setLlmModel(m.v)}
                    >
                      <div className="am-radio-card-name">{m.name}</div>
                      <div className="am-radio-card-cost">{m.cost}</div>
                      <div className="am-radio-card-tag">{m.tag}</div>
                    </div>
                  ))}
                </div>
              </div>

              <div className="am-set-stats">
                <div><span className="lbl">За сегодня</span><span className="v">$0.42</span></div>
                <div><span className="lbl">За 30 дней</span><span className="v">$28.15</span></div>
                <div><span className="lbl">Запросов сегодня</span><span className="v">1,420</span></div>
                <div><span className="lbl">Средняя цена</span><span className="v">$0.0003</span></div>
              </div>
            </div>

            <div className="am-set-card">
              <div className="am-set-card-h">
                <div>
                  <div className="am-set-card-title">Avito-сессия</div>
                  <div className="am-set-card-sub">Cookie для парсинга закрытых страниц</div>
                </div>
                <span className="am-pill am-pill-ok">● Активна</span>
              </div>
              <div className="am-set-row">
                <label className="am-set-label">Статус сессии</label>
                <div className="am-info-grid">
                  <div><span className="lbl">User-ID</span><span className="v">u_28419405</span></div>
                  <div><span className="lbl">Истекает</span><span className="v">через 14 дней</span></div>
                  <div><span className="lbl">Регион</span><span className="v">Москва (ms)</span></div>
                  <div><span className="lbl">Прокси</span><span className="v">RU-residential ×3</span></div>
                </div>
                <div style={{display:'flex',gap:8,marginTop:12}}>
                  <button className="am-btn am-btn-sm">Перевыпустить</button>
                  <button className="am-btn am-btn-sm">Тест-запрос</button>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* NOTIFICATIONS */}
        {tab === 'notifications' && (
          <div className="am-settings-pane">
            <div className="am-set-card">
              <div className="am-set-card-h">
                <div>
                  <div className="am-set-card-title">Telegram</div>
                  <div className="am-set-card-sub">Основной канал для алертов</div>
                </div>
                <label className="am-switch">
                  <input type="checkbox" checked={tgEnabled} onChange={e => setTgEnabled(e.target.checked)}/>
                  <span className="am-switch-track"><span className="am-switch-thumb"></span></span>
                </label>
              </div>

              {tgEnabled && (
                <>
                  <div className="am-set-row">
                    <label className="am-set-label">Bot token</label>
                    <input className="am-input" type="password" defaultValue="7420198350:AAGxK..." style={{fontFamily:'var(--font-mono)',fontSize:13}}/>
                  </div>
                  <div className="am-set-row">
                    <label className="am-set-label">Chat ID</label>
                    <div style={{display:'flex',gap:8,alignItems:'center'}}>
                      <input className="am-input" defaultValue="-1002847291038" style={{fontFamily:'var(--font-mono)',fontSize:13,flex:1}}/>
                      <button className="am-btn am-btn-sm">Тест-сообщение</button>
                    </div>
                    <div className="am-set-hint">Канал «Avito Monitor — kostya», 1 участник</div>
                  </div>

                  <div className="am-set-row">
                    <label className="am-set-label">Триггеры</label>
                    <div className="am-checkbox-group">
                      {[
                        {id:'new_alert', label:'Новый лот в alert-зоне', sub:'основной use-case', checked:true},
                        {id:'price_drop', label:'Падение цены > 5%', sub:'у уже отслеживаемых лотов', checked:true},
                        {id:'historical_low', label:'Исторический минимум за 30 дней', sub:'', checked:true},
                        {id:'market_trend', label:'Сдвиг медианы рынка > 5% за неделю', sub:'агрегатные события', checked:false},
                        {id:'condition_mix', label:'Изменение mix состояний', sub:'может быть шумно', checked:false},
                      ].map(t => (
                        <label key={t.id} className="am-checkbox-row">
                          <input type="checkbox" defaultChecked={t.checked}/>
                          <div>
                            <div className="am-checkbox-label">{t.label}</div>
                            {t.sub && <div className="am-checkbox-sub">{t.sub}</div>}
                          </div>
                        </label>
                      ))}
                    </div>
                  </div>

                  <div className="am-set-row">
                    <label className="am-set-label">Тихие часы</label>
                    <div style={{display:'flex',gap:8,alignItems:'center'}}>
                      <input className="am-input" defaultValue="23:00" style={{width:90}}/>
                      <span style={{color:'var(--text-muted)',fontSize:13}}>—</span>
                      <input className="am-input" defaultValue="08:00" style={{width:90}}/>
                      <span style={{fontSize:12,color:'var(--text-muted)',marginLeft:8}}>копятся в digest</span>
                    </div>
                  </div>
                </>
              )}
            </div>

            <div className="am-set-card">
              <div className="am-set-card-h">
                <div>
                  <div className="am-set-card-title">Email</div>
                  <div className="am-set-card-sub">Бэкап-канал, дайджест раз в день</div>
                </div>
                <label className="am-switch">
                  <input type="checkbox" checked={emailEnabled} onChange={e => setEmailEnabled(e.target.checked)}/>
                  <span className="am-switch-track"><span className="am-switch-thumb"></span></span>
                </label>
              </div>
              {!emailEnabled && (
                <div style={{padding:'8px 4px',fontSize:13,color:'var(--text-muted)'}}>Выключено. Включи если Telegram недоступен.</div>
              )}
            </div>
          </div>
        )}

        {/* PARSING */}
        {tab === 'parsing' && (
          <div className="am-settings-pane">
            <div className="am-set-card">
              <div className="am-set-card-title" style={{marginBottom:16}}>Расписание polling</div>

              <div className="am-set-row">
                <label className="am-set-label">Интервал опроса (минуты)</label>
                <div className="am-poll-slider">
                  <input
                    type="range"
                    min={1}
                    max={30}
                    step={1}
                    value={pollInterval}
                    onChange={e => setPollInterval(+e.target.value)}
                    className="am-range"
                  />
                  <div className="am-poll-readout">
                    <span className="v">{pollInterval}</span>
                    <span className="u">мин</span>
                  </div>
                </div>
                <div className="am-poll-marks">
                  <span>1 мин</span><span>5</span><span>15</span><span>30 мин</span>
                </div>
                <div className="am-set-hint">
                  ≈ {Math.round(60/pollInterval * 24 * 3)} запросов/день на 3 активных профиля. Avito лимит ≈ 600/час с одного IP.
                </div>
              </div>

              <div className="am-set-row">
                <label className="am-set-label">Расписание</label>
                <div className="am-radio-row">
                  {['24/7','08:00–23:00','По дням'].map((opt,i) => (
                    <label key={opt} className={`am-radio-pill ${i===0 ? 'active' : ''}`}>
                      <input type="radio" name="schedule" defaultChecked={i===0}/>
                      <span>{opt}</span>
                    </label>
                  ))}
                </div>
              </div>

              <div className="am-set-row">
                <label className="am-set-label">Поведение при ошибках</label>
                <div className="am-info-grid">
                  <div><span className="lbl">Ретраи</span><span className="v">3 попытки, экспоненц.</span></div>
                  <div><span className="lbl">При 429</span><span className="v">пауза 5 мин</span></div>
                  <div><span className="lbl">При капче</span><span className="v">смена IP</span></div>
                  <div><span className="lbl">Уведомить если</span><span className="v">5+ fail подряд</span></div>
                </div>
              </div>
            </div>

            <div className="am-set-card">
              <div className="am-set-card-title" style={{marginBottom:12}}>Очистка данных</div>
              <div className="am-set-row">
                <label className="am-set-label">Хранить историю лотов</label>
                <select className="am-input" defaultValue="90" style={{maxWidth:240}}>
                  <option value="30">30 дней</option>
                  <option value="90">90 дней (рекоменд.)</option>
                  <option value="180">180 дней</option>
                  <option value="365">1 год</option>
                  <option value="0">Не удалять</option>
                </select>
                <div className="am-set-hint">Сейчас в БД: 4,832 лота · 18 МБ</div>
              </div>
            </div>
          </div>
        )}

        {/* BILLING */}
        {tab === 'billing' && (
          <div className="am-settings-pane">
            <div className="am-set-card am-billing-hero">
              <div className="am-billing-month">Апрель 2026</div>
              <div className="am-billing-total">$28.15</div>
              <div className="am-billing-bd">
                <div className="am-billing-row">
                  <span>Anthropic LLM</span><span className="v">$26.40</span>
                  <div className="am-billing-bar"><span style={{width:'93%'}}></span></div>
                </div>
                <div className="am-billing-row">
                  <span>Прокси (residential)</span><span className="v">$1.50</span>
                  <div className="am-billing-bar"><span style={{width:'5%'}}></span></div>
                </div>
                <div className="am-billing-row">
                  <span>Telegram bot hosting</span><span className="v">$0.25</span>
                  <div className="am-billing-bar"><span style={{width:'1%'}}></span></div>
                </div>
              </div>
              <div className="am-billing-foot">
                <span>Бюджет: <strong>$50/мес</strong></span>
                <span style={{color:'var(--positive)'}}>Прогноз к концу: $33</span>
              </div>
            </div>

            <div className="am-set-card">
              <div className="am-set-card-title" style={{marginBottom:12}}>Лимиты и алерты</div>
              <div className="am-set-row">
                <label className="am-set-label">Месячный потолок</label>
                <div style={{display:'flex',gap:8,alignItems:'center'}}>
                  <span style={{fontSize:14,color:'var(--text-secondary)'}}>$</span>
                  <input className="am-input" defaultValue="50" style={{width:120,fontFamily:'var(--font-mono)'}}/>
                  <span style={{fontSize:13,color:'var(--text-muted)'}}>при достижении — пауза polling</span>
                </div>
              </div>
              <div className="am-set-row">
                <label className="am-set-label">Алерт по email при</label>
                <div className="am-radio-row">
                  {['50%','75%','90%'].map((v,i) => (
                    <label key={v} className={`am-radio-pill ${i===1?'active':''}`}>
                      <input type="radio" name="bcap" defaultChecked={i===1}/>
                      <span>{v} от бюджета</span>
                    </label>
                  ))}
                </div>
              </div>
            </div>

            <div className="am-set-card">
              <div className="am-set-card-title" style={{marginBottom:8}}>История</div>
              <table className="am-table">
                <thead><tr><th>Месяц</th><th>LLM</th><th>Прокси</th><th>Хостинг</th><th>Итого</th></tr></thead>
                <tbody>
                  <tr><td>Апрель 2026</td><td>$26.40</td><td>$1.50</td><td>$0.25</td><td><strong>$28.15</strong></td></tr>
                  <tr><td>Март 2026</td><td>$31.20</td><td>$1.50</td><td>$0.25</td><td><strong>$32.95</strong></td></tr>
                  <tr><td>Февраль 2026</td><td>$24.80</td><td>$1.50</td><td>$0.25</td><td><strong>$26.55</strong></td></tr>
                  <tr><td>Январь 2026</td><td>$19.10</td><td>$1.50</td><td>$0.25</td><td><strong>$20.85</strong></td></tr>
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* ACCOUNT */}
        {tab === 'account' && (
          <div className="am-settings-pane">
            <div className="am-set-card">
              <div style={{display:'flex',gap:16,alignItems:'center',marginBottom:20}}>
                <div style={{width:64,height:64,borderRadius:'50%',background:'var(--brand)',display:'grid',placeItems:'center',fontSize:24,fontWeight:700,color:'#fff'}}>K</div>
                <div>
                  <div style={{fontSize:18,fontWeight:600}}>kostya</div>
                  <div style={{fontSize:13,color:'var(--text-muted)'}}>kostya@gmail.com · с января 2026</div>
                </div>
              </div>
              <div className="am-set-row">
                <label className="am-set-label">Имя пользователя</label>
                <input className="am-input" defaultValue="kostya" style={{maxWidth:320}}/>
              </div>
              <div className="am-set-row">
                <label className="am-set-label">Email</label>
                <input className="am-input" defaultValue="kostya@gmail.com" style={{maxWidth:320}}/>
              </div>
              <div className="am-set-row">
                <label className="am-set-label">Часовой пояс</label>
                <select className="am-input" defaultValue="Europe/Moscow" style={{maxWidth:320}}>
                  <option>Europe/Moscow (UTC+3)</option>
                  <option>Europe/Kaliningrad (UTC+2)</option>
                  <option>Asia/Yekaterinburg (UTC+5)</option>
                </select>
              </div>
            </div>

            <div className="am-set-card">
              <div className="am-set-card-title" style={{marginBottom:12}}>Безопасность</div>
              <div className="am-sec-row">
                <div>
                  <div style={{fontWeight:500}}>Пароль</div>
                  <div style={{fontSize:12,color:'var(--text-muted)'}}>Изменён 18.03.2026</div>
                </div>
                <button className="am-btn am-btn-sm">Сменить</button>
              </div>
              <div className="am-sec-row">
                <div>
                  <div style={{fontWeight:500}}>Двухфакторка</div>
                  <div style={{fontSize:12,color:'var(--text-muted)'}}>Не настроена</div>
                </div>
                <button className="am-btn am-btn-sm am-btn-primary">Включить</button>
              </div>
              <div className="am-sec-row">
                <div>
                  <div style={{fontWeight:500}}>Активные сессии</div>
                  <div style={{fontSize:12,color:'var(--text-muted)'}}>2 устройства · MacBook Pro, iPhone</div>
                </div>
                <button className="am-btn am-btn-sm">Управлять</button>
              </div>
            </div>
          </div>
        )}

        {/* DANGER */}
        {tab === 'danger' && (
          <div className="am-settings-pane">
            <div className="am-set-card am-danger-card">
              <div className="am-danger-row">
                <div>
                  <div className="am-danger-title">Экспорт всех данных</div>
                  <div className="am-danger-sub">JSON со всеми профилями, лотами и историей. ≈ 18 МБ.</div>
                </div>
                <button className="am-btn am-btn-sm">Скачать .json</button>
              </div>
              <div className="am-danger-row">
                <div>
                  <div className="am-danger-title">Сбросить историю лотов</div>
                  <div className="am-danger-sub">Удалит все накопленные данные. Профили останутся.</div>
                </div>
                <button className="am-btn am-btn-sm am-btn-danger">Сбросить</button>
              </div>
              <div className="am-danger-row">
                <div>
                  <div className="am-danger-title">Удалить аккаунт</div>
                  <div className="am-danger-sub">Безвозвратно. Данные сотрутся через 30 дней.</div>
                </div>
                <button className="am-btn am-btn-sm am-btn-danger">Удалить</button>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

window.ScreenSettings = ScreenSettings;

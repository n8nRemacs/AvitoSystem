# avito-frontend / src / components

**Назначение:** Reusable Vue-компоненты, сгруппированные по доменам.

**Статус:** not_used_in_v1.

---

## Группы

- `auth/` — TokenStatus, TokenDetails, SessionHistory, SessionUpload, RemoteBrowser (Playwright WS), AlertBanner
- `farm/` — DeviceList, BindingTable
- `layout/` — AppHeader, AppSidebar
- `messenger/` — ChannelList, ChatWindow, MessageBubble, ComposeBox, CallHistory
- `search/` — SearchForm, ItemCard, ItemDetail

---

## Заметка для V1

Компоненты мессенджера и search могут быть референсом для HTMX-шаблонов по структуре данных и UX-поведению.

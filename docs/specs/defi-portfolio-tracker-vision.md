# DeFi Portfolio Tracker — Project Vision

**Status:** DRAFT  
**Date:** 2026-02-15  
**Context:** Logical evolution of DeFi Sentinel Scout bot → full portfolio management platform

---

## User Decisions (locked)

| Question | Decision |
|----------|----------|
| UI | **Web interface** + **Telegram alerts** |
| Chains v1 | **Base, Arbitrum, Polygon, Hyper EVM** (all EVM) |
| Chains v2 | All major EVM + **Solana** |
| Business model | **Self-hosted** (personal) → **SaaS subscription** if works well |
| History depth | **Full tx history** — parse everything from wallet creation |
| Non-EVM timing | **Later phase** — Solana after EVM chains are stable |

---

## Positioning

```
┌──────────────────────────────────────────────────┐
│           DeFi Sentinel Platform                 │
│                                                  │
│  ┌──────────────┐    ┌────────────────────────┐  │
│  │  Scout Bot   │    │  Portfolio Tracker      │  │
│  │  (Alpha)     │◄──►│  (Observability)       │  │
│  │              │    │                        │  │
│  │ • Find pools │    │ • See all positions    │  │
│  │ • Score      │    │ • Track PnL           │  │
│  │ • Recommend  │    │ • Manage strategies   │  │
│  │ • Alert      │    │ • Risk dashboard      │  │
│  └──────────────┘    └────────────────────────┘  │
│         │                      │                 │
│         └──────────┬───────────┘                 │
│                    ▼                             │
│          ┌──────────────────┐                    │
│          │  Execution Layer │  (v2 — future)     │
│          │  • Auto-rebalance│                    │
│          │  • Claim rewards │                    │
│          │  • Exit rules    │                    │
│          └──────────────────┘                    │
└──────────────────────────────────────────────────┘
```

**Scout** находит **куда** входить. **Tracker** показывает **что** происходит после входа. Вместе = полный цикл управления DeFi портфелем.

---

## Что пользователь описал

| Фича | Описание |
|------|----------|
| Авто-детект позиций | LP (Uniswap), lending (Aave), HLP (Hyperliquid) — подключаешь кошелёк, всё подтягивается |
| Мульти-чейн | 9 chains: ETH, Base, Arbitrum, Solana + 5 |
| Мульти-кошелёк | Несколько кошельков → агрегированный дашборд |
| Фильтры по типу | LP, lending, borrows, wallet balances — каждый отдельно |
| Стратегии | Группировка позиций с разных чейнов в одну "стратегию" |

---

## Чего не хватает для полноценного управления

### Слой 1: Observability (видеть)

**1.1 PnL Tracking** — самый важный пробел
- Текущий P&L по каждой позиции (unrealized)
- Исторический P&L (realized): когда открыл, по какой цене, что заработал
- **IL tracking** для LP позиций (сколько потерял от impermanent loss vs hold)
- **Fee/reward income** разбивка: сколько заработал fees, сколько rewards
- **Cost basis** для налогов: сумма инвестиций → текущая стоимость → прибыль

```
Позиция: ETH/USDC LP на Aerodrome Base
├── Вложено: $1,000 (0.3 ETH + 500 USDC) @ ETH=$1,667
├── Текущая стоимость: $1,085
├── Fees earned: +$42
├── AERO rewards: +$18 (claimed $12, pending $6)
├── IL: -$15 (ETH вырос → ты потерял vs hold)
├── Gas spent: -$0.35
└── Net PnL: +$44.65 (+4.5%)
```

**1.2 Transaction History**
- Авто-парсинг on-chain транзакций → привязка к позициям
- Декодирование: swaps, mints, burns, claims, borrows, repays
- Таймлайн: когда что делал, на какой цене

**1.3 Portfolio-Level Analytics**
- Exposure по активам: 40% ETH, 30% USDC, 20% AERO, 10% ARB
- Exposure по чейнам: 60% Base, 25% Arbitrum, 15% ETH mainnet
- Exposure по протоколам: 50% Aerodrome, 30% Aave, 20% Uniswap
- **Concentration risk**: "80% капитала в одном протоколе — опасно"

---

### Слой 2: Risk Management (защищать)

**2.1 Liquidation Monitor** — критично для lending
- Health factor tracking (Aave, Morpho, Compound)
- Алерт: "Health factor < 1.5 — пополни залог или верни часть долга"
- Liquidation price visualization: "ETH < $1,200 → ликвидация"
- **Cascading risk**: "Если ETH -20%, что произойдёт со всеми позициями?"

**2.2 Strategy Drift Monitor**
- Целевая аллокация стратегии: 60/40 stable/volatile
- Текущая: 45/55 (дрифт из-за роста ETH)
- Рекомендация: "Rebalance: продай $100 ETH/USDC LP, добавь $100 в stable LP"

**2.3 Protocol Risk Layer**
- Аудит-статус протокола (audited/unaudited)
- TVL тренд (растёт/падает → сигнал здоровья)
- Smart contract risk rating (integrated from external sources)

---

### Слой 3: Intelligence (предлагать)

**3.1 Reward Harvesting**
- Pending rewards по всем позициям: "$6 AERO, $3 OP, $12 ARB"
- Оптимальный момент для claim: "claim когда сумма > $20 (чтобы gas не съел)"
- Auto-compound рекомендация: "Reinvest rewards в ту же позицию?"

**3.2 Strategy Performance Benchmarking**
- Твоя стратегия "ETH Bull" заработала 12% за месяц
- Benchmark: холд ETH дал бы 8%, risk-free (Aave USDC) дал бы 3%
- Sharpe ratio, max drawdown, volatility — professional metrics

**3.3 Tax Estimation**
- YTD income от DeFi: fees $X, rewards $Y, realized gains $Z
- Экспорт в CSV для CoinTracker/Koinly/ручной расчёт

**3.4 Scout ↔ Tracker Integration**
- Scout нашёл пул → Tracker показывает: "У тебя уже есть позиция в этом протоколе на 30% портфеля. Добавлять ещё — concentration risk."
- Tracker видит: "Позиция ETH/USDC вне range 6 часов" → Scout ищет альтернативу: "Вот пул с лучшим band_depth для текущей цены"

---

## Архитектура: Что строить

```
┌─────────────────────────────────────────────────────────────┐
│                      Frontend (Web App)                      │
│  Dashboard │ Positions │ Strategies │ Analytics │ Alerts     │
└─────────────────────────┬───────────────────────────────────┘
                          │
┌─────────────────────────▼───────────────────────────────────┐
│                      API Layer                               │
│  /wallets │ /positions │ /strategies │ /pnl │ /alerts        │
└─────────────────────────┬───────────────────────────────────┘
                          │
┌─────────────────────────▼───────────────────────────────────┐
│                  Position Resolver                           │
│                                                              │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐       │
│  │ EVM      │ │ Solana   │ │ Lending  │ │ Perps    │       │
│  │ LP       │ │ LP       │ │ Resolver │ │ Resolver │       │
│  │ Resolver │ │ Resolver │ │          │ │          │       │
│  │          │ │          │ │ Aave     │ │ Hyper-   │       │
│  │ Uni v3   │ │ Orca     │ │ Morpho   │ │ liquid   │       │
│  │ Aero     │ │ Raydium  │ │ Compound │ │          │       │
│  │ Velo     │ │          │ │          │ │          │       │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘       │
│                                                              │
│                    ┌──────────────┐                          │
│                    │ Chain        │                          │
│                    │ Adapters     │                          │
│                    │              │                          │
│                    │ EVM RPC ×7   │                          │
│                    │ Solana RPC   │                          │
│                    │ + subgraphs  │                          │
│                    └──────────────┘                          │
└─────────────────────────────────────────────────────────────┘
                          │
┌─────────────────────────▼───────────────────────────────────┐
│                  Data Store                                   │
│  Positions │ Snapshots │ Transactions │ PnL │ Strategies     │
│                    (SQLite → Postgres)                        │
└─────────────────────────────────────────────────────────────┘
```

---

## Цепочки и протоколы

### Phase 1 (v1 launch — 4 EVM chains)

| Chain | LP DEXes | Lending | Perps |
|-------|----------|---------|-------|
| **Base** | Aerodrome, Uniswap v3 | Aave v3, Morpho | — |
| **Arbitrum** | Uniswap v3, Camelot | Aave v3, Radiant | — |
| **Polygon** | Uniswap v3, QuickSwap | Aave v3 | — |
| **Hyper EVM** | HyperSwap (CL) | — | HLP vaults |

### Phase 2 (расширение EVM)

| Chain | LP DEXes | Lending | Perps |
|-------|----------|---------|-------|
| Ethereum | Uniswap v3 | Aave v3, Morpho | — |
| Optimism | Velodrome, Uniswap v3 | Aave v3 | — |
| BSC | PancakeSwap v3 | Venus | — |
| Avalanche | Trader Joe, Uniswap v3 | Aave v3 | — |

### Phase 3 (non-EVM)

| Chain | LP DEXes | Lending | Perps |
|-------|----------|---------|-------|
| **Solana** | Orca, Raydium | Marginfi, Kamino | — |

> **Примечание:** Solana — не EVM. Нужен отдельный адаптер (SVM + Anchor). Hyper EVM — EVM-совместимый, поэтому в Phase 1.

---

## Roadmap

### Phase 1: MVP (6-8 недель)

| Компонент | Scope |
|-----------|-------|
| Chains | **4 chains:** Base, Arbitrum, Polygon, Hyper EVM |
| Protocols | Aerodrome, Uniswap v3, Aave v3, HyperSwap/HLP |
| Wallets | Мульти-кошелёк + агрегация |
| Positions | Авто-детект LP + lending + perps (HLP) |
| PnL | Текущая стоимость + unrealized PnL |
| History | **Полная история tx** с момента создания кошелька |
| Strategies | Ручная группировка позиций |
| UI | **Web dashboard** (read/write) |
| Alerts | **Telegram:** OOR LP, health factor, reward claim reminder |
| Deploy | Self-hosted (VPS, как Scout) |

### Phase 2: Глубина (4-6 недель)
- Исторический PnL + realized gains/losses
- IL tracking для LP позиций
- Strategy performance: benchmark vs hold, vs risk-free
- +4 EVM chains (ETH, Optimism, BSC, Avalanche)
- Concentration risk dashboard

### Phase 3: Intelligence + Non-EVM (6-8 недель)
- **Solana** адаптер (Orca, Raydium, Marginfi)
- Scout ↔ Tracker integration
- Reward harvesting рекомендации
- Tax export (CSV / CoinTracker format)
- Strategy drift alerts

### Phase 4: SaaS (будущее, если всё работает)
- Multi-tenant architecture
- User auth + subscription billing
- Public API
- Execution layer (auto-claim, auto-rebalance) — **только после валидации ручного режима**

---

## Ключевые технические решения

### 1. Position Resolver Pattern

Каждый протокол требует уникальной логики для обнаружения позиций:

```python
class PositionResolver(Protocol):
    """Interface for protocol-specific position detection."""
    
    async def resolve_positions(self, wallet: str, chain: str) -> List[Position]:
        """Scan on-chain state for wallet's positions in this protocol."""
        ...
    
    def supported_chains(self) -> List[str]: ...
    def position_type(self) -> Literal["lp", "lending", "borrow", "perps", "wallet"]: ...
```

| Протокол | Как находить позиции |
|----------|----------------------|
| Uniswap v3 | Query `NonfungiblePositionManager.balanceOf(wallet)` → get NFT IDs → `positions(tokenId)` |
| Aerodrome CL | Аналогично Uniswap v3 + проверка стейкинга в gauge |
| Aave v3 | Query `Pool.getUserAccountData(wallet)` + `getReservesList()` + `aToken/debtToken` balances |
| Orca (Solana) | Parse wallet ATAs → find Orca position NFTs → deserialize on-chain account data |
| Hyperliquid | REST API (off-chain order book, не on-chain) |

### 2. Snapshot vs Real-Time

| Тип данных | Метод | Частота |
|------------|-------|---------|
| Позиции (есть/нет) | RPC call | Каждые 5 мин |
| Стоимость позиции | RPC + price feed | Каждые 1 мин |
| PnL расчёт | Snapshot diff | Каждые 15 мин |
| Alerts (OOR, health) | RPC / WebSocket | Каждые 10-60 сек |
| Transaction history | Subgraph / indexer | On-demand |

### 3. Data Model (Core)

```python
class Wallet(BaseModel):
    address: str
    chain: str
    label: str  # "Main", "Trading", "Cold"

class Position(BaseModel):
    id: str                    # Unique across all chains
    wallet: Wallet
    protocol: str              # "aerodrome", "aave_v3", "uniswap_v3"
    chain: str
    position_type: Literal["lp", "supply", "borrow", "perps", "wallet_balance"]
    
    # Value
    value_usd: float
    cost_basis_usd: Optional[float]
    unrealized_pnl_usd: Optional[float]
    
    # LP-specific
    lp_details: Optional[LPDetails]   # tokens, range, fees_accrued, IL
    
    # Lending-specific
    lending_details: Optional[LendingDetails]  # apy, health_factor, liquidation_price
    
    # Metadata
    last_updated: datetime
    data_quality: Literal["FRESH", "STALE", "ERROR"]

class Strategy(BaseModel):
    name: str                          # "ETH Bull", "Stable Yield", "Arbitrage"
    positions: List[str]               # Position IDs
    target_allocation: Optional[Dict]  # {"ETH": 0.6, "USDC": 0.4}
    created_at: datetime

class Portfolio(BaseModel):
    wallets: List[Wallet]
    positions: List[Position]
    strategies: List[Strategy]
    total_value_usd: float
    total_pnl_usd: float
```

---

## Конкуренты — чем вдохновляться

| Продукт | Что делает хорошо | Чего не хватает |
|---------|-------------------|-----------------|
| **Zapper** | Авто-детект, мульти-чейн | Нет стратегий, слабый PnL |
| **DeBank** | Лучший мульти-чейн tracker | Нет LP-specific метрик (IL, fees) |
| **Revert Finance** | Лучший Uniswap v3 tracker (IL, fees, range) | Только Uni v3, нет lending |
| **DeFi Saver** | Automation + portfolio | Только Ethereum mainnet |
| **Zerion** | Красивый UI, хорошая агрегация | Нет глубокой LP аналитики |

**Наше преимущество:** Scout + Tracker в одной системе. Ни один конкурент не совмещает **поиск возможностей** + **трекинг позиций** + **стратегии**. Плюс Hyperliquid HLP — нишевый, но растущий рынок.

---

## Tech Stack (locked)

| Компонент | Решение | Обоснование |
|-----------|---------|-------------|
| **Frontend** | Next.js (React) | Самый популярный, лучшая документация, подходит для SaaS |
| **Backend** | Python + FastAPI | Уже есть Scout на Python, переиспользуем код |
| **БД** | PostgreSQL | Сразу, без миграций SQLite→Postgres |
| **RPC** | Alchemy | Поддерживает все 4 chain, готовые SDK, бесплатный tier |
| **Tx History** | The Graph | Уже подключен в Scout |
| **Auth (v1)** | Wallet-based (SIWE) | Sign-In with Ethereum, без паролей |
| **Auth (SaaS)** | Email + subscription | Stripe/Lemon Squeezy для биллинга |
| **Deploy** | Текущий VPS (рядом со Scout) → Cloud (SaaS) | Один сервер, общая инфра |
| **Alerts** | Telegram Bot API | Уже есть в Scout |

## Решённые вопросы

| # | Вопрос | Решение |
|---|--------|--------|
| 1 | UI | Web dashboard (Next.js) + Telegram alerts |
| 2 | Chains v1 | Base, Arbitrum, Polygon, Hyper EVM |
| 3 | Chains v2+ | Все крупные EVM → Solana |
| 4 | Business model | Self-hosted → SaaS subscription |
| 5 | История | Полная (с момента создания кошелька) |
| 6 | Non-EVM | Solana позже, после стабильного EVM |
| 7 | Paywall | Решим после MVP (варианты: лимит кошельков, chains, история) |

## Открытые вопросы

1. **Дизайн:** тёмная тема? Стиль? Вдохновение (Zapper, DeBank, Zerion)?
2. **Hosting:** какой VPS (текущий Scout сервер или отдельный)?

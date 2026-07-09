# Переезд Zubchek с Atoms (MGX) на свою инфраструктуру

Документ описывает, как отвязать приложение от платформы Atoms и развернуть его
на своих серверах: где держать **сервер**, где **базу/облако** и куда подключать
**домен**. Данные переносить не нужно — проект в бета-тесте, базу поднимаем
пустой.

---

## 1. Что уже сделано в этой ветке

| Изменение | Файл(ы) |
|-----------|---------|
| Пример переменных окружения для backend | `.env.example` |
| Пример переменных для frontend | `frontend/.env.example` |
| Dockerfile для backend | `backend/Dockerfile`, `backend/.dockerignore` |
| Локальный/прод стек (Postgres + backend) | `docker-compose.yml` |
| Убраны build-плагины Atoms из Vite | `frontend/vite.config.ts` |
| Убраны зависимости Atoms из package.json | `frontend/package.json` |
| Своя замена SDK `@metagptx/web-sdk` на axios | `frontend/src/lib/mgxClient.ts` (+ правки импортов в `lib/api.ts`, `lib/auth.ts`, `pages/SharedReport.tsx`) |

Атомс-специфичного в коде больше не осталось. Проприетарный OSS-шлюз
(`services/storage.py`) можно оставить неактивным — фронтенд его не вызывает,
фото хранятся в БД.

---

## 2. Архитектура после переезда

```
                    ┌──────────────────────────┐
   Пользователь ──▶ │  Frontend (статика, SPA) │   app.ВАШ-ДОМЕН
                    │  Cloudflare Pages / Vercel│
                    └───────────┬──────────────┘
                                │  HTTPS, VITE_API_BASE_URL
                                ▼
                    ┌──────────────────────────┐
                    │  Backend (FastAPI/Docker) │   api.ВАШ-ДОМЕН
                    │  Railway / Render / VPS   │
                    └─────┬───────────────┬─────┘
                          │               │
                          ▼               ▼
                 ┌────────────────┐  ┌──────────────┐
                 │ Postgres (Neon)│  │ AI-провайдер │  (OpenAI-совместимый)
                 └────────────────┘  └──────────────┘
```

---

## 3. Рекомендуемый стек (дёшево, под бету, для соло-разработчика)

| Слой | Рекомендация | Почему | Цена |
|------|--------------|--------|------|
| **База данных** | **Neon** (serverless Postgres) | Уже Postgres, щедрый free-tier, ветвление | Free |
| **Backend** | **Railway** (Docker) | Простой деплой из Git, managed Postgres рядом, свой домен | ~$5/мес |
| **Frontend** | **Cloudflare Pages** | Глобальный CDN, бесплатно, SPA-роутинг из коробки | Free |
| **AI** | **OpenAI** или **OpenRouter** | OpenAI-совместимый API, есть vision-модели | по факту |
| **DNS / домен** | **Cloudflare** | Бесплатный DNS, проксирование, SSL | Free |
| **Объектное хранилище** | не нужно | фото лежат в БД | — |

> Альтернативы: backend — **Render** (есть free-tier с «засыпанием»), фронт —
> **Vercel**, база — Postgres прямо в Railway. Логика одинаковая.

---

## 4. Пошаговый деплой

### Шаг A — База данных (Neon)
1. Зарегистрируйся на [neon.tech](https://neon.tech), создай проект `zubchek`.
2. Скопируй **connection string** (вида `postgresql://user:pass@ep-xxx.neon.tech/db`).
3. Он пойдёт в переменную `DATABASE_URL` backend'а.
   Таблицы создадутся автоматически при первом старте (см. `create_tables`).

### Шаг B — Backend (Railway)
1. Создай проект на [railway.app](https://railway.app), **Deploy from GitHub repo**.
2. Root directory → `backend` (там лежит `Dockerfile`). Railway соберёт образ.
3. В **Variables** добавь переменные из `.env.example`:
   - `DATABASE_URL` — строка из Neon (Шаг A)
   - `APP_AI_BASE_URL`, `APP_AI_KEY` — из Шага D
   - `JWT_SECRET_KEY` — длинная случайная строка
   - `ENVIRONMENT=prod`, `FRONTEND_URL=https://app.ВАШ-ДОМЕН`
   - `PORT` Railway задаёт сам — трогать не нужно.
4. После деплоя Railway даст URL вида `https://zubchek-backend.up.railway.app`.
   Проверь `/{URL}/health` → `{"status":"healthy"}` и `/{URL}/docs` (Swagger).

### Шаг C — Frontend (Cloudflare Pages)
1. На [pages.cloudflare.com](https://pages.cloudflare.com) → **Create → Connect to Git**.
2. Настройки сборки:
   - Framework preset: **Vite**
   - Root directory: `frontend`
   - Build command: `pnpm i && pnpm build`
   - Build output: `dist`
3. В **Environment variables** задай:
   - `VITE_API_BASE_URL=https://api.ВАШ-ДОМЕН`  (URL backend'а из Шага B/E)
4. Deploy. Cloudflare даст `https://zubchek.pages.dev`.

### Шаг D — AI-ключ
- **OpenAI:** `APP_AI_BASE_URL=https://api.openai.com/v1`, `APP_AI_KEY=sk-...`
- **OpenRouter** (доступ к Claude/GPT/др.): `APP_AI_BASE_URL=https://openrouter.ai/api/v1`, ключ из кабинета.
- Для анализа зубов нужна **vision-модель** — проверь, что выбранная модель принимает изображения.

### Шаг E — Домен и DNS (Cloudflare)
1. Добавь домен в Cloudflare (или зарегистрируй новый), переведи NS на Cloudflare.
2. Настрой поддомены:

| Поддомен | Куда указывает | Как |
|----------|----------------|-----|
| `app.ВАШ-ДОМЕН` (или корень) | Frontend (Cloudflare Pages) | В Pages → **Custom domains** → добавить домен, Cloudflare сам создаст запись |
| `api.ВАШ-ДОМЕН` | Backend (Railway) | В Railway → **Settings → Networking → Custom Domain**, скопировать целевой хост и создать **CNAME** `api` → `xxx.up.railway.app` |

3. После привязки домена обнови переменные и передеплой:
   - Frontend: `VITE_API_BASE_URL=https://api.ВАШ-ДОМЕН`
   - Backend: `FRONTEND_URL=https://app.ВАШ-ДОМЕН`

---

## 5. Куда какая переменная идёт (шпаргалка)

| Переменная | Где задаётся | Значение |
|------------|--------------|----------|
| `DATABASE_URL` | Backend (Railway) | строка Neon |
| `APP_AI_BASE_URL` / `APP_AI_KEY` | Backend | ваш AI-провайдер |
| `JWT_SECRET_KEY` | Backend | случайная строка |
| `FRONTEND_URL` | Backend | `https://app.ВАШ-ДОМЕН` |
| `VITE_API_BASE_URL` | Frontend (Pages) | `https://api.ВАШ-ДОМЕН` |
| `STRIPE_SECRET_KEY` | Backend | если нужны оплаты |
| `OIDC_*` | Backend | опционально (см. п.7) |

---

## 6. Локальный запуск (для разработки)

**Backend + Postgres** одной командой (нужен Docker Desktop):
```bash
cp .env.example .env      # впиши APP_AI_KEY и т.д.; DATABASE_URL можно не трогать
docker compose up --build
# backend: http://localhost:8000  (Swagger: /docs)
```

**Frontend** (нужен Node.js 20+ и pnpm — на этой машине их сейчас НЕТ, поставь):
```bash
cd frontend
corepack enable            # включает pnpm
pnpm i                     # пересоберёт lockfile без пакетов Atoms
pnpm dev                   # http://localhost:3000, /api проксируется на :8000
```

---

## 7. Что осталось / на что обратить внимание

- ⚠️ **Проверить сборку фронтенда с Node.** Замену SDK (`mgxClient.ts`) я не смог
  собрать локально — на машине не установлен Node. После `pnpm i && pnpm build`
  убедись, что билд проходит и логин/анализ/отчёты работают.
- 🔒 **Безопасность auth.** Сейчас доступ построен на header-based `custom-auth`
  (`X-User-Id`/`X-User-Role`), без проверки подписи — любой может выдать себя за
  другого. Для продакшена стоит перейти на нормальный вход (свой OIDC:
  Auth0/Clerk/Cognito/Keycloak → заполнить `OIDC_*`) или подписанные JWT.
- 🧹 **Lockfile.** `pnpm-lock.yaml` ещё содержит старые пакеты Atoms — первый
  `pnpm i` (без `--frozen-lockfile`) их уберёт.
- 🗑 **OSS-роутер** (`routers/storage.py`, `services/storage.py`) не используется
  фронтендом. Можно удалить целиком или оставить — на работу не влияет.
- 📦 **`lambda_handler.py`** больше не нужен при деплое через Docker — оставлен на
  случай, если захочешь вернуться на AWS Lambda.
- 🌐 **CORS** сейчас открыт на все домены (`allow_origin_regex=".*"`). После
  привязки домена сузь до `FRONTEND_URL` в `backend/main.py`.

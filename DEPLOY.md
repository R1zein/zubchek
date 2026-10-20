# Zubchek — инфраструктура и деплой

Актуальное состояние продакшена. Заменяет старый `MIGRATION.md` (тот описывал
промежуточный стек Neon + Railway + Cloudflare Pages, который выведен из
эксплуатации).

---

## 1. Где всё живёт

Весь прод — **один VPS в Timeweb Cloud (Москва)**, всё в Docker.

| Слой | Что | Где |
|------|-----|-----|
| VPS | Ubuntu 22.04, 2 vCPU / 4 GB / 50 GB NVMe | `104.171.132.55`, каталог `/opt/zubchek` |
| Frontend | Vite SPA (статика) | Caddy отдаёт из `/opt/zubchek/frontend-dist` → `zubchek.com`, `www` |
| Backend | FastAPI в Docker | Caddy проксирует `api.zubchek.com` → `backend:8000` |
| База | PostgreSQL 18 в контейнере | том смонтирован в `/var/lib/postgresql` |
| TLS | Caddy + Let's Encrypt, автопродление | сертификаты на все три хоста |
| Фото и бэкапы | Timeweb S3 | `s3.twcstorage.ru`, бакет `zubchek-photos` |
| DNS | Cloudflare, **проксирование выключено** (серые облака) | A-записи → IP VPS |
| Почта | Resend | коды входа + отправка PDF-отчётов |
| AI | Claude Sonnet 5 через Cloudflare Worker-релей | см. §4 |

Причина такой схемы: из России без VPN Cloudflare-прокси и зарубежный хостинг
режутся РКН, плюс 152-ФЗ требует хранить персональные и медданные в РФ.
Cloudflare остался **только как authoritative DNS**, трафик через него не идёт.

### Объектное хранилище

```
S3_ENDPOINT_URL=https://s3.twcstorage.ru
S3_REGION=ru-1
S3_BUCKET=zubchek-photos
S3_PUBLIC_BASE_URL=https://s3.twcstorage.ru/zubchek-photos   # path-style
```

Раскладка в бакете: `reports/<uuid>.<ext>` — фото отчётов, `backups/` — ночные
дампы БД. Листинг бакета закрыт, объекты читаются по прямой ссылке.

Код: [`backend/services/s3_storage.py`](backend/services/s3_storage.py). Если
хранилище не сконфигурировано или аплоад упал — фото остаётся base64 в БД,
ничего не ломается.

---

## 2. Бэкапы

`/opt/zubchek/backup.sh` по крону (`/etc/cron.d/zubchek-backup`) в 03:00:
`pg_dump` → gzip → S3 `backups/`, хранится последние 14.

⚠️ Восстановление ни разу не проверялось на практике — стоит хоть раз прогнать
тестовый рестор в отдельную базу.

---

## 3. Как передеплоить

**Backend:**
```bash
# с локальной машины: залить исходники в /opt/zubchek, затем на сервере
docker compose build backend && docker compose up -d backend
```

**Frontend:**
```bash
# сборка в контейнере node:20-alpine с VITE_API_BASE_URL=https://api.zubchek.com
# затем обновить содержимое frontend-dist, НЕ удаляя сам каталог:
find frontend-dist -mindepth 1 -delete && cp -r dist/. frontend-dist/
docker compose restart caddy
```

> ⚠️ **Главная грабля.** Caddy бинд-маунтит `frontend-dist` по inode. Если
> сделать `rm -rf frontend-dist && cp -r dist frontend-dist`, маунт порвётся и
> сайт целиком отдаст **404**. Поэтому либо чистить содержимое на месте (как
> выше), либо после замены обязательно `docker compose restart caddy`.

Ещё: у фронта есть service worker — после деплоя пользователям может
потребоваться Ctrl+F5.

---

## 4. AI-релей (обязательно к пониманию)

`api.anthropic.com` отдаёт **403** с российского IP (геоблок Cloudflare).
Поэтому запросы идут через бесплатный Cloudflare Worker, который прозрачно
проксирует на Anthropic; секретный префикс в пути гейтит посторонних.
Ключ Anthropic лежит только на сервере и просто пробрасывается дальше.

```
APP_AI_BASE_URL=https://<worker>.workers.dev/<секретный-префикс>/v1
APP_AI_MODEL=claude-sonnet-5
```

Если релей отвалится, AI **тихо деградирует**, а не падает: валидация фото
становится разрешающей, детекция брекетов пропадает, рекомендации остаются
статическими. Числовой Z-индекс при этом продолжает считаться — он пиксельный,
не AI. Это коварно: снаружи выглядит работающим. При подозрении — проверять
логи бэкенда на 403.

Разделение ответственности:
- **Z-индекс (проценты налёта)** — чистая пиксельная математика,
  [`services/pixel_analysis.py`](backend/services/pixel_analysis.py).
- **AI** — валидация («это зубы?», «есть краситель?»), детекция ортодонтии и
  аттачментов, текст рекомендаций.

⚠️ **152-ФЗ, нерешённое.** Фото уходят из РФ в Anthropic (США). Комплаентный
вариант на будущее — российская vision-модель (YandexGPT / GigaChat).

---

## 5. Валидация фото

Два слоя, порядок важен:
1. Дешёвый пиксельный пре-чек: `tooth_coverage < 6` → «нет зубов»,
   `stained_area < 4` → «нет красителя».
2. Авторитетная проверка моделью в `detect_ortho_and_recommend`: сначала
   `is_teeth`, затем `has_dye`.

Промпт второго слоя должен быть **нейтральным**. Если в нём утверждать «на фото
зубы», модель всегда соглашается и валидация становится бесполезной.

---

## 6. Локальная разработка

```bash
cp .env.example .env      # вписать APP_AI_KEY и прочее; DATABASE_URL можно не трогать
docker compose up --build
```
Backend на `http://localhost:8000` (Swagger `/docs`), Postgres на `5432`.

```bash
cd frontend
corepack enable
pnpm i
pnpm dev                  # http://localhost:3000, /api проксируется на :8000
```

Переменные — шпаргалка:

| Переменная | Где | Значение |
|------------|-----|----------|
| `DATABASE_URL` | backend | локально — из compose; на проде — контейнер `db` |
| `APP_AI_BASE_URL` / `APP_AI_KEY` / `APP_AI_MODEL` | backend | релей + Sonnet 5 |
| `ANALYSIS_CONCURRENCY` | backend | 2 — семафор вокруг тяжёлого анализа, чтобы 4 ГБ не улетели в своп |
| `JWT_SECRET_KEY` | backend | длинная случайная строка |
| `S3_*` | backend | Timeweb S3 |
| `RESEND_API_KEY` / `EMAIL_FROM` | backend | почта |
| `VITE_API_BASE_URL` | frontend, на этапе сборки | `https://api.zubchek.com` |

Секреты живут только в `/opt/zubchek/.env` (chmod 600) — не в гите и не в чате.

---

## 7. Известный технический долг

- 🔒 **Аутентификация.** Часть доступа построена на header-based `custom-auth`
  (`X-User-Id` / `X-User-Role`) без проверки подписи — теоретически можно выдать
  себя за другого пользователя. Это самый серьёзный пункт списка. Заполненные
  `OIDC_*` или честные подписанные JWT закрывают вопрос.
- 🌐 **CORS** открыт на всё (`allow_origin_regex=".*"` в `backend/main.py`) —
  сузить до `FRONTEND_URL`.
- 📧 Resend: бесплатный тариф 3000/мес и **100/день** — второй лимит реальнее.
  Отправка требует настоящего `User-Agent`: Resend за Cloudflare, а
  `Python-urllib` там ловит бан 1010.
- 🗑 OSS-роутер (`routers/storage.py`, `services/storage.py`) не используется
  фронтендом — кандидат на удаление.
- 📦 `lambda_handler.py` не нужен при Docker-деплое.
- 💾 Бэкап-рестор не проверен (см. §2).

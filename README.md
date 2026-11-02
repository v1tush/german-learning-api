# German Learning API

A Django Ninja API for learning German vocabulary. It manages a shared word catalogue, personal word lists and tags, datasets, translations, study schedules, review cards, and site notifications. PostgreSQL stores the data; Redis carries Celery tasks; Celery Beat and a worker run scheduled reviews. Translation suggestions can use Yandex Cloud AI.

The repository contains the API and the server-side Telegram linking flow. A Telegram bot and delivery of study words through Telegram are not implemented yet.

## Run with Docker Compose

Docker Compose runs PostgreSQL, Redis, the Django development server, a Celery worker, and Celery Beat. The web server, migration job, worker, and Beat all use the same image built from the root `Dockerfile`; Redis uses the official `redis:alpine` image. Run these commands from the repository root:

```sh
# If .env does not already exist, copy .env.example to .env.
cp .env.example .env
# Edit .env: replace the sample secrets and database password; add Yandex Cloud credentials if needed.
docker compose up --build -d
```

The one-off `migrate` service applies database migrations before `web`, `worker`, and `beat` start. After later schema changes, rebuild with `docker compose up --build -d` to rerun it. API routes are under `http://localhost:8000/api/`, with interactive OpenAPI documentation at <http://localhost:8000/api/docs>. The Django admin is at <http://localhost:8000/admin/>. To create an admin account, run:

```sh
docker compose exec web python manage.py createsuperuser
```

Use `docker compose logs -f web worker beat` to inspect the application processes and `docker compose down` to stop them. The Compose stack is intended for development: `web` uses Django's `runserver` and binds to the host's loopback interface. Keep only one Beat instance running so each schedule is dispatched once per minute. PostgreSQL, Redis, and uploaded media use persistent Docker volumes.

Compose services are named `web`, `worker`, `beat`, `migrate`, `redis`, and `db`. Inside Compose, `DB_HOST` is set to `db` and `CELERY_BROKER_URL` is set to `redis://redis:6379/0`; local processes can use the host and broker values in `.env` instead. Single-quote `.env` values containing `$` so Compose passes them through unchanged.

## Configuration

Copy `.env.example` to `.env` and set the values before starting Django. The project reads `.env` from the project directory or a parent directory. Never commit `.env` or real credentials.

| Variable | Purpose |
| --- | --- |
| `DJANGO_SECRET_KEY` | Django signing secret; use a long random value. |
| `DJANGO_DEBUG` | Enable development debug mode (`true` or `false`). |
| `DJANGO_ALLOWED_HOSTS` | Comma-separated hosts accepted by Django. |
| `JWT_SECRET_KEY` | Secret used to sign access and refresh JWTs; use a different long random value. |
| `ALGORITHMS` | Comma-separated allowed JWT algorithms, such as `HS256`. |
| `TG_BOT_AUTH_KEY` | Shared API key for trusted Telegram bot requests. |
| `YANDEX_CLOUD_FOLDER`, `YANDEX_CLOUD_API_KEY`, `YANDEX_CLOUD_MODEL` | Yandex Cloud AI configuration for translation generation. |
| `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT` | PostgreSQL connection settings. Compose provides the database host. |
| `CELERY_BROKER_URL` | Redis URL for Celery. Compose provides its internal Redis URL. |

Yandex Cloud is contacted when a translation suggestion or a card answer needs to be generated. Browsing already saved words and translations does not call the AI service.

## Run without Compose

Install Python 3.14 or newer, [uv](https://docs.astral.sh/uv/), PostgreSQL, and Redis. Create a PostgreSQL database and set the `DB_*` variables in `.env` to match it. The default local Redis URL is `redis://localhost:6379/0`.

From the repository root:

```sh
# If .env does not already exist, copy .env.example to .env.
cp .env.example .env
# Edit .env, then start PostgreSQL and Redis.
uv sync
cd german_learning_api
uv run python manage.py migrate
uv run python manage.py runserver
```

Start the worker and Beat in two more terminals from `german_learning_api`:

```sh
uv run celery -A german_learning_api worker --loglevel=info
```

```sh
uv run celery -A german_learning_api beat --loglevel=info
```

Celery does not officially support running workers directly on Windows; use Docker or WSL there. Beat creates a local `celerybeat-schedule` state file, which is ignored by Git.

## Tests and checks

The Django test suite uses a PostgreSQL test database. From the repository root, with PostgreSQL configured:

```sh
cd german_learning_api
uv run python manage.py test
```

With Compose running, use:

```sh
docker compose exec web python manage.py test
```

Run the configured linter from the repository root with `uv run ruff check .`.

## Authentication and API routes

The API is mounted under `/api/`. `POST /api/authentication/register` and `POST /api/authentication/login` return an access token and set an HTTP-only refresh cookie. Send the access token as `Authorization: Bearer <access_token>` on user routes. `POST /api/authentication/refresh` rotates the refresh token; `POST /api/authentication/logout` revokes it. `GET /api/users/me/` returns the signed-in user's profile.

Most personal resources also accept bot authentication with `X-API-Key` and `X-Telegram-ID` after the Telegram account has been linked. The site notification routes require a user access token. The interactive API documentation lists the full request and response schemas.

| Area | Useful routes |
| --- | --- |
| Words | `GET /api/words/pages/{sort}/{page}`, `GET /api/words/{word_id}`, `GET /api/words/me` |
| Tags and datasets | `/api/tags/`, `/api/datasets/`, `GET /api/datasets/{dataset_id}/words` |
| Translations | `GET /api/translations/words/{word_id}/translations`, `POST /api/translations/words/{word_id}/translation-suggestions` |
| Schedules and cards | `/api/schedules/`, `GET /api/schedules/{schedule_id}/cards` |
| Notifications | `GET /api/notifications/`, `POST /api/notifications/{notification_id}/read` |

The public catalogue page route requires `sort` (`id` or `popular`) and a one-based `page` number. It returns at most 100 words with `page`, `sort`, `page_size`, and `has_next`. `popular` orders by the current number of users who added a word, then by ascending ID. An out-of-range page returns an empty `words` list. The old `GET /api/words` list route is no longer available.

### Telegram account linking

A signed-in site user calls `POST /api/users/me/telegram-link` with an access token. The response contains a one-use `token` and an `expires_at` timestamp ten minutes in the future. Calling it again invalidates the previous token. A client can pass the token to a future bot using `https://t.me/<bot_username>?start=<token>`.

After receiving `/start <token>` in a private chat, the bot should call `POST /api/users/telegram-link/confirm` with `{"token": "..."}`, `X-API-Key` containing the bot's shared key, and `X-Telegram-ID` containing the message sender's Telegram ID. This is the only request that writes a user's `telegram_id`; a site client cannot assign an arbitrary ID. Expired or used tokens, and Telegram IDs linked to another user, are rejected. Once linked, bot authentication resolves the user by `X-Telegram-ID`; the current ID is visible at `GET /api/users/me/`.

### Translations and word forms

`GET /api/translations/words/{word_id}/translations` reads saved translations for the user's current language. `POST /api/translations/words/{word_id}/translation-suggestions` returns saved variants if a non-empty main translation exists. Otherwise it requests suggestions from Yandex Cloud AI, stores them, and chooses a main translation. Non-main saved variants alone do not prevent generation. If AI finds no translation, the response still includes previously saved non-main variants.

Translations are compared after Unicode NFC normalization, case folding, and collapsing whitespace. When a generated variant matches a saved variant, the saved spelling is retained. A review card takes its answer from a non-empty `custom_translation`, then a translation selected by the user for the current language, then a main translation. If the card has no answer, `POST /api/schedules/{schedule_id}/cards/{user_word_id}/resolve-answer` can generate and save one. Listing cards never triggers bulk AI generation.

Word forms are available through `GET` and `POST /api/words/{word_id}/inflections` and `GET`, `PATCH`, and `DELETE /api/words/{word_id}/inflections/{inflection_id}`. Creation requires a `type` such as `de_partizip_2` and a non-empty `value`; updates may change either field. Each word has at most one form of each type. Users may read forms for words in their own vocabulary; only active staff users may create, update, or delete forms, including through bot authentication. The API validates that a form type matches the word's language and part of speech. Forms belong to the shared `Word`, so edits are visible to everyone who has that word.

### Import German forms from UniMorph

The `import_unimorph_de` management command imports German Partizip II (`de_partizip_2`), preterite (`de_prateritum`), and plural (`de_plural`) forms from a pinned revision of [UniMorph/deu](https://github.com/unimorph/deu). Its source is English Wiktionary, licensed CC BY-SA 3.0. The command downloads and verifies that revision unless you provide a local file with `--file /path/to/deu`.

The command is a preview by default; add `--apply` to write data. `--scope existing` fills forms for German words already in the database. `--scope all` also creates words with unambiguous forms and can add tens of thousands of shared words. Existing forms are never overwritten, and ambiguous or conflicting forms can be inspected in a TSV report. The import does not use AI.

For example, from `german_learning_api` in a local checkout:

```sh
uv run python manage.py import_unimorph_de --scope existing --report unimorph-report.tsv
uv run python manage.py import_unimorph_de --scope existing --apply --report unimorph-report.tsv
```

With Compose, run the same command through `docker compose exec web python manage.py ...`. If the report is written to `/tmp/unimorph-report.tsv` in the container, copy it to the host with `docker compose cp web:/tmp/unimorph-report.tsv ./unimorph-report.tsv`.

### Datasets and schedules

A dataset combines words in selected tags with individually selected user words. Create one with `POST /api/datasets/` using `name`, an array of tag IDs in `tags`, and an array of **UserWord** IDs in `extra_words` (from `GET /api/words/me`). `PATCH /api/datasets/{dataset_id}` changes its composition; `GET /api/datasets/{dataset_id}/words` returns its current words without duplicates. The server checks that the tags and individual words belong to the caller.

Tags are kept as dataset references, so a word added to a selected tag later automatically enters the dataset. An explicitly added word remains even if it has none of the selected tags. Several schedules can share a dataset, and changes to that dataset affect their future runs. A dataset used by a schedule cannot be deleted.

To create a schedule, send `dataset_id` to `POST /api/schedules/`; `null` means all of the user's words. `PATCH /api/schedules/{schedule_id}` can change it later. `mode` is `interval` or `fixed_times`. `exercise_kind` is `translation` or `inflection`. An inflection exercise requires an `inflection_type`, such as `de_partizip_2`; a translation exercise requires `inflection_type: null`. New schedule requests must include `dataset_id`, even when it is `null`.

Only words with status `learning` are eligible; inflection exercises also require the requested form. At creation, enough eligible words must exist to fill `items_per_delivery`, even for a disabled schedule. If the number later falls below that limit, the current delivery is skipped and the next time is calculated from the schedule. Selection prefers words never shown for this exercise type, then words shown on earlier days, and finally repeats from today if needed.

The migration from older tag-based schedules creates a separate dataset named `Расписание #<id>` for each schedule that had tags. Older schedules without tags retain `dataset_id: null` and continue to use all learning words.

### Site notifications and review cards

Each schedule run creates one site notification. A client can poll `GET /api/notifications/` once a minute; it returns unread notifications by default, while `?unread_only=false` includes read ones. `POST /api/notifications/{notification_id}/read` marks one as read without disabling its schedule or changing `next_run_at`. The notification includes `schedule_id` and `dataset_id` so the client can open the review.

`GET /api/schedules/{schedule_id}/cards` returns the current dataset's words with their status, answer, and answer source. With `dataset_id: null`, it returns all of the user's words. A Quizlet-style client can select `learning` words, shuffle them, and display cards. For an inflection exercise, `answer` is the requested form; for a translation exercise, it follows the translation priority described above. A missing answer is `null`, so the client can omit that card or request translation generation with `resolve-answer`.

### Background schedule processing

Celery Beat enqueues `dispatch_due_schedules` every minute. That task finds enabled schedules whose `next_run_at` is due and enqueues `process_due_schedule` for each one. The worker creates a `ScheduleRun`, selects its words, calculates the next due time, and writes the site notification in the same transaction. A row lock and due-time check prevent a duplicate run if the task is queued twice. Run only one Beat instance.

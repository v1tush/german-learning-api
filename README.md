# German Learning API

A Django Ninja API for learning German vocabulary. It manages a shared word catalogue, personal word lists and tags, datasets, translations, study schedules, review cards, and site notifications. PostgreSQL stores the data; Redis carries Celery tasks; Celery Beat and a worker run scheduled reviews. Translation suggestions can use Yandex Cloud AI.

The repository also contains Wozzi, an aiogram Telegram bot for account onboarding, adding and browsing saved words, managing personal tags and datasets, browsing schedules, and profile editing. Delivery of study words through Telegram is not implemented yet.

## Run with Docker Compose

Docker Compose runs PostgreSQL, Redis, the Django development server, Wozzi, a Celery worker, and Celery Beat. The `migrate` service builds `german-learning-api:local` once from the root `Dockerfile`; `web`, `bot`, `worker`, and `beat` reuse that local image. Redis uses the official `redis:alpine` image. Run these commands from the repository root:

```sh
# If .env does not already exist, copy .env.example to .env.
cp .env.example .env
# Edit .env: replace the sample secrets and database password; add Yandex Cloud credentials if needed.
docker compose up --build -d
```

The one-off `migrate` service applies database migrations before `web`, `bot`, `worker`, and `beat` start. After later schema changes, rebuild with `docker compose up --build -d` to rerun it. API routes are under `http://localhost:8000/api/`, with interactive OpenAPI documentation at <http://localhost:8000/api/docs>. The Django admin is at <http://localhost:8000/admin/>. To create an admin account, run:

```sh
docker compose exec web python manage.py createsuperuser
```

Use `docker compose logs -f web bot worker beat` to inspect the application processes and `docker compose down` to stop them. The Compose stack is intended for development: `web` uses Django's `runserver` and binds to the host's loopback interface. Keep only one Beat instance running so each schedule is dispatched once per minute. PostgreSQL, Redis, and uploaded media use persistent Docker volumes.

Compose services are named `web`, `bot`, `worker`, `beat`, `migrate`, `redis`, and `db`. Inside Compose, `DB_HOST` is set to `db`, `CELERY_BROKER_URL` is set to `redis://redis:6379/0`, and Wozzi calls `http://web:8000/api`; local processes can use the host values in `.env` instead. Single-quote literal `$NAME` sequences in `.env` so Compose preserves them. Avoid `${NAME}` in secrets: `python-dotenv`, which parses `.env` for `environs`, expands that syntax even inside single quotes.

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
| `TELEGRAM_BOT_TOKEN` | Telegram Bot API token used by Wozzi. |
| `WOZZI_API_BASE_URL` | Base URL of Django's `/api` routes, reachable from the bot process. |
| `WOZZI_FSM_REDIS_URL` | Redis database for bot conversation state; use a separate database from Celery. |
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

To start Wozzi locally in another terminal, run `uv run python -m telegram_bot.main` from `german_learning_api`. It needs the API, Redis, `TELEGRAM_BOT_TOKEN`, and `TG_BOT_AUTH_KEY`.

Celery does not officially support running workers directly on Windows; use Docker or WSL there. Beat creates a local `celerybeat-schedule` state file, which is ignored by Git.

## Tests and checks

The Django test suite uses a PostgreSQL test database. From the repository root, with PostgreSQL configured:

```sh
cd german_learning_api
uv run python manage.py test
uv run python -m unittest telegram_bot.tests
```

With Compose running, use:

```sh
docker compose exec web python manage.py test
docker compose exec bot python -m unittest telegram_bot.tests
```

Run the configured linter from the repository root with `uv run ruff check .`.

To run Ruff automatically before each local commit, install the Git hook once from the repository root:

```sh
uv run pre-commit install
```

The hook runs `ruff check --fix` and then `ruff format` on staged Python files. If Ruff changes a file, review and stage the change before committing again. GitHub does not run local Git hooks; a GitHub Actions workflow is needed to check pull requests on GitHub.

## Authentication and API routes

The API is mounted under `/api/`. `POST /api/authentication/register` and `POST /api/authentication/login` return an access token and set an HTTP-only refresh cookie. Send the access token as `Authorization: Bearer <access_token>` on user routes. `POST /api/authentication/refresh` rotates the refresh token; `POST /api/authentication/logout` revokes it. `GET /api/users/me/` returns the signed-in user's profile. `PATCH /api/users/me/` updates the username, email, interface language, and learning language. `POST /api/users/me/avatar` uploads a JPEG, PNG, or WebP avatar as multipart field `avatar`; authenticated `GET /api/users/me/avatar` returns the image, and `DELETE /api/users/me/avatar` removes it.

Most personal resources also accept bot authentication with `X-API-Key` and `X-Telegram-ID` after the Telegram account has been linked. The site notification routes require a user access token. The interactive API documentation lists the full request and response schemas.

| Area | Useful routes |
| --- | --- |
| Words | `GET /api/words/pages/{sort}/{page}`, `GET /api/words/{word_id}`, `GET /api/words/me` |
| Tags and datasets | `/api/tags/`, `/api/datasets/`, `GET /api/datasets/{dataset_id}/words` |
| Translations | `GET /api/translations/words/{word_id}/translations`, `POST /api/translations/words/{word_id}/translation-suggestions` |
| Schedules and cards | `/api/schedules/`, `GET /api/schedules/{schedule_id}/cards` |
| Notifications | `GET /api/notifications/`, `POST /api/notifications/{notification_id}/read`, `POST /api/notifications/read-all` |

The public catalogue page route requires `sort` (`id` or `popular`) and a one-based `page` number. It returns at most 100 words with `page`, `sort`, `page_size`, and `has_next`. `popular` orders by the current number of users who added a word, then by ascending ID. An out-of-range page returns an empty `words` list. The old `GET /api/words` list route is no longer available.

### Wozzi account onboarding and Telegram linking

In a private chat, `/start` uses the Telegram sender's `language_code` as the initial interface language when it is Russian, English, or German. For other codes it asks the user to choose. The guest welcome screen offers account creation, account linking, an interface-language switch, and support. Once an account is linked, its saved interface language takes precedence. `/start` and `/menu` open a separate main menu with words, tags, datasets, schedules, account, and support. Words can be added and browsed; tags and datasets can be created, edited, and deleted; schedules remain browse-only, and the bot does not yet send study cards. Account opens a photo message with the saved avatar (or a generated initial), profile details, an editing prompt, the editing buttons, and a main-menu button. Saving changes or cancelling an edit returns to that screen. Support opens a chat with `@v1tush` with the Telegram user ID in a prepared draft; the user chooses whether to send it. `/settings` remains a command shortcut to the account screen, `/help` explains the available actions, and `/cancel` leaves the current form for its parent screen. The linking screen explains how to use a personal link without sending users to the placeholder `wozzi.com` site.

For a new user, the bot asks for a username and learning language, then calls `POST /api/users/telegram-register` with its `X-API-Key` and the actual Telegram sender's ID in `X-Telegram-ID`. The API creates an already linked user with an unusable password. Bot-created accounts cannot sign in to the website with a password until a separate password setup or Telegram sign-in flow is built. The bot can then edit the profile and upload or remove the avatar through the user API using `aiohttp`; it never connects to the ORM directly. FSM state lives in Redis so restarts do not discard an in-progress form.

A signed-in site user calls `POST /api/users/me/telegram-link` with an access token. The response contains a one-use `token` and an `expires_at` timestamp ten minutes in the future. Calling it again invalidates the previous token. A client passes the token to the bot using `https://t.me/<bot_username>?start=<token>`.

After receiving `/start <token>` in a private chat, the bot calls `POST /api/users/telegram-link/confirm` with `{"token": "..."}`, `X-API-Key` containing the bot's shared key, and `X-Telegram-ID` containing the message sender's Telegram ID. The site client cannot assign an arbitrary Telegram ID. Expired or used tokens, and Telegram IDs linked to another user, are rejected. Once linked, bot authentication resolves the user by `X-Telegram-ID`; the current ID is visible at `GET /api/users/me/`. The website still needs a UI to issue and open the link; the API flow already works.

### Wozzi word entry and vocabulary

`Word.language` is the profile's `current_learning_language`; translation `target_language` is `current_using_language` (for example, German `Haus` → Russian `дом`). `Word`, `BaseTranslation`, and word forms are shared catalogue data. `UserWord` is the personal vocabulary entry; `UserWordTranslation` stores that user's selected shared variants, optional custom variant, and `is_card_primary` flags. One bot form collects these separate records. Changing interface language changes which personal translations are shown without deleting selections for another language.

**Add word** in **My words** starts a Redis-backed FSM: enter a Unicode-normalized word of 1–255 characters with collapsed whitespace; choose noun, verb, adjective, or adverb; choose translations; choose primary translations; review; save. After part of speech, `POST /api/words/` gets or creates the shared Word, then the bot checks for a personal duplicate. An existing entry opens without overwriting its translations. The shared Word is needed to read saved variants from `GET /api/translations/words/{word_id}/translations`; cancelling after this point leaves the shared Word in the catalogue but does not add a personal entry.

Translation buttons toggle at most five saved `BaseTranslation` variants. The user may also type one custom translation of at most 500 characters; the same value cannot be selected as both a saved and custom variant. **Suggest translations** explicitly calls `POST /api/translations/words/{word_id}/translation-suggestions`; it uses saved variants when a main one exists and may call Yandex Cloud AI otherwise. Suggestion failure leaves manual entry available. The inline keyboard keeps translation choices neutral; suggestion and custom-entry actions use Telegram's blue primary style, removal uses red danger, and Next/Save use green success. Save without translation uses blue primary. Telegram clients may adapt the preset colors to their theme. With any translation selected, the next FSM screen lists only those selections, including the custom one, and requires one or two to be marked primary. The confirmation screen marks primary choices with stars. `POST /api/words/me` creates the personal entry with one `translation_selection`; the API enforces the five-plus-one and one-or-two limits. **Save without translation** skips the primary step. `/cancel` and the form's Cancel button return to My words.

My words shows all personal entries by default. **Translated** shows only entries with at least one personally selected shared or custom translation for the current interface language; a shared suggestion alone does not qualify. The read-only detail shows the shared word language, part of speech, available forms, the user's selected translations (stars mark primary; the custom one is labelled), status, and hint. Forms are read through `GET /api/words/{word_id}/inflections`; regular users cannot change shared forms through the bot. Transcription exists in `WordProperties` but is not exposed by the current API or detail screen.

The future Quizlet-style Telegram card should reveal the one or two personally selected primary translations, then offer **Show more translations** only for that user's remaining selections. The current `ReviewCardOut` still returns one `answer` and can fall back to the shared main translation; extend its response and translation-card eligibility before implementing this card UI. A word without a personal translation stays in My words, but should not enter that future translation practice. Tags have a separate section from datasets: users can create and delete personal tags, add or remove words from a tag, and manage tags from a word's detail screen. Either direction updates the same relation and any dataset that uses that tag. Deleting a tag requires confirmation because it can change those datasets.

The word detail offers a red **Delete word** action. It requires a confirmation in the bot's FSM, calls DELETE /api/words/me/{user_word_id}, and returns to the same list filter and page with a notice. This deletes the user's personal entry and its selected translations, not the shared Word, shared translations, or other users' entries. Historical schedule items keep their records with a null word reference. Deleting a personal entry does not clean up a shared Word created before the personal save.

### Translations and word forms

`GET /api/translations/words/{word_id}/translations` reads saved translations for the user's current language, including each variant's `id`. `POST /api/translations/words/{word_id}/translation-suggestions` returns saved variants if a non-empty main translation exists. Otherwise it requests suggestions from Yandex Cloud AI, stores them, and chooses a main translation. Non-main saved variants alone do not prevent generation. If AI finds no translation, the response still includes previously saved non-main variants.

Translations are compared after Unicode NFC normalization, case folding, and collapsing whitespace. When a generated variant matches a saved variant, the saved spelling is retained. `POST /api/words/me` and `PATCH /api/words/me/{user_word_id}` accept an optional `translation_selection` object with `base_translation_ids`, `primary_base_translation_ids`, `custom_translation`, and `custom_is_card_primary`. It replaces the selection for the user's current language; omit it in a patch to leave the selection unchanged, or send empty arrays and no custom text to clear it. A word can have up to five saved variants plus one custom translation, with one or two marked for immediate display when a selection is present. The response includes the saved selection under `translation_selection`.

For example, `POST /api/words/me` accepts `{"word_id": 42, "translation_selection": {"base_translation_ids": [10, 11], "primary_base_translation_ids": [10], "custom_translation": "my wording", "custom_is_card_primary": true}}`. The response's `translation_selection.base_translations` contains each selected variant's ID, text, and `is_card_primary`; it also includes the custom text and its primary flag.

Until the card interface is extended, a translation review card uses the first selected primary translation as its single `answer`. If no primary is selected, it falls back to the shared main translation. `POST /api/schedules/{schedule_id}/cards/{user_word_id}/resolve-answer` can generate and save a missing shared translation. Listing cards never triggers bulk AI generation. The shared `is_main` flag does not determine a user's primary choices.

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

In the Telegram bot, open **Sets** from the main menu to create a set, select tags and individual words, then save it. The same screen lets you rename a set, change its sources, or delete it after confirmation. Selection changes are saved together; `/cancel` discards an unfinished form. A set referenced by a schedule remains available and the bot explains why deletion was blocked.

To create a schedule, send `dataset_id` to `POST /api/schedules/`; `null` means all of the user's words. `PATCH /api/schedules/{schedule_id}` can change it later. `mode` is `interval` or `fixed_times`. `exercise_kind` is `translation` or `inflection`. An inflection exercise requires an `inflection_type`, such as `de_partizip_2`; a translation exercise requires `inflection_type: null`. New schedule requests must include `dataset_id`, even when it is `null`.

Only words with status `learning` are eligible; inflection exercises also require the requested form. At creation, enough eligible words must exist to fill `items_per_delivery`, even for a disabled schedule. If the number later falls below that limit, the current delivery is skipped and the next time is calculated from the schedule. Selection prefers words never shown for this exercise type, then words shown on earlier days, and finally repeats from today if needed.

The migration from older tag-based schedules creates a separate dataset named `Расписание #<id>` for each schedule that had tags. Older schedules without tags retain `dataset_id: null` and continue to use all learning words.

### Site notifications and review cards

Each schedule run creates one site notification. A client can poll `GET /api/notifications/` once a minute; it returns unread notifications by default, while `?unread_only=false` includes read ones. `POST /api/notifications/{notification_id}/read` marks one as read without disabling its schedule or changing `next_run_at`. `POST /api/notifications/read-all` marks all unread notifications of the signed-in user as read and returns `204 No Content`. The notification includes `schedule_id` and `dataset_id` so the client can open the review.

`GET /api/schedules/{schedule_id}/cards` returns the current dataset's words with their status, answer, and answer source. With `dataset_id: null`, it returns all of the user's words. A Quizlet-style client can select `learning` words, shuffle them, and display cards. For an inflection exercise, `answer` is the requested form; for a translation exercise, it follows the translation priority described above. A missing answer is `null`, so the client can omit that card or request translation generation with `resolve-answer`.

### Background schedule processing

Celery Beat enqueues `dispatch_due_schedules` every minute. That task finds enabled schedules whose `next_run_at` is due and enqueues `process_due_schedule` for each one. The worker creates a `ScheduleRun`, selects its words, calculates the next due time, and writes the site notification in the same transaction. A row lock and due-time check prevent a duplicate run if the task is queued twice. Run only one Beat instance.

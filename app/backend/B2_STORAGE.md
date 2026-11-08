# Приватные изображения в Backblaze B2 / S3

## Архитектура

`services/image_storage.py` заменяет прежний сервис локальных файлов:

- `ImageStorage` — асинхронный интерфейс upload/download/delete/close, без SQL,
  пользователей или проверок владельца.
- `S3ImageStorage` — реализация через boto3. Endpoint, регион, bucket и credentials
  берутся из существующего `Settings`; имя bucket не зашито в реализацию.
- Один низкоуровневый boto3 client создаётся на worker при startup и переиспользуется.
  Клиент закрывается при shutdown. Указаны SigV4, явные credentials, path addressing,
  connect timeout 5 с, read timeout 15 с, один attempt без автоматического retry.
  Необязательные AWS checksum trailers отключены для S3-совместимости.
- Синхронные SDK-вызовы, чтение чанков и закрытие StreamingBody выполняются в
  thread pool, не в event loop. Download отдаётся чанками по 64 KiB, тело закрывается
  также при ошибке, отмене и disconnect до первого чтения.
- Ключ `images/<uuid4>.<extension>` формируется на backend. MIME/расширение берутся
  из сигнатуры декодированных байтов: JPEG, PNG, WebP, GIF. Неизвестные форматы
  отклоняются (502), а не сохраняются с ложным расширением `.jpg`.
- PUT содержит `ContentType` и `IfNoneMatch="*"`: существующий объект не
  перезаписывается даже при случайной коллизии UUID. Нет public ACL или presigned URL.
- Storage не создаёт и не переводит bucket в публичный режим. Оператор должен
  заранее выбрать **private bucket** и ограниченный им обычный B2 Application Key.

Используются уже изменённая ORM-модель с `object_key` и существующая миграция.
Новых миграций, таблиц, Engine, очередей или системы авторизации не добавлено.
Зависимость boto3 уже присутствовала в пользовательских `pyproject.toml` / `uv.lock`;
её установка проверена через `uv sync --locked`.

## Генерация и транзакции

Проверки модели/владельца, owner advisory lock, глобальный слот, Token Bucket и
дневной бюджет сохранены. Cloudflare по-прежнему получает только текущий prompt.
Его HTTP deadline — общий `asyncio.timeout(60.0)`, не только сетевой httpx timeout.

После Cloudflare объект загружается в S3. Только подтверждённый PUT позволяет
начать короткую транзакцию сохранения чата, генерации с `object_key` и updated_at.
Во время Cloudflare **и PUT** SQL-транзакции нет. Обе advisory locks удерживаются
на том же соединении до окончания PUT, сохранения или обработки ошибки.
Перед PUT дополнительно проверяется соединение, удерживающее locks.
Сохранение гостевой генерации и перенос гостя используют единый порядок коротких
row locks: guest → chat → generation. Это предотвращает потерю только что
сохранённого чата при одновременной регистрации и FK cascade удаления гостя.

Отмена await не останавливает boto3 thread. Поэтому отменённый запрос дожидается
завершения SDK-операции, прежде чем отпустить locks. Не применяется `wait_for`,
который вернул бы соединение/слот, оставив загрузку в работающем потоке.

### Ошибки и компенсация

- Ошибка Cloudflare: 502, без PUT и успешной генерации.
- Ошибка/неподтверждённый PUT: 503, без успешной записи. Кандидат object_key
  записывается в административный лог. Сбой ответа не доказывает, что PUT не
  произошёл; автоматического удаления нет, в частности при конфликте conditional PUT.
- Ошибка до начала COMMIT с подтверждённым rollback: внутренний delete объекта.
- COMMIT с окончательным серверным отказом (SQLSTATE классов 23/40): после rollback
  также разрешена компенсация.
- Потерянный/неизвестный ответ COMMIT, cancellation во время COMMIT или ошибка
  rollback: объект **не удаляется**. Запрос завершается ошибкой, но запись могла
  быть зафиксирована; удаление могло бы сломать уже сохранённую историю.
- Ошибка delete логируется как orphan для административной очистки и не заменяет
  исходную ошибку сохранения. Публичного DELETE API нет.

Дневная reservation не возвращается при ошибках Cloudflare/B2/сохранения.
Семантика Token Bucket, Neurons и глобального параллелизма не изменена.

## Контракты API

### POST /Text-to-Masterpiece/generate

Запрос прежний: prompt, model_id, необязательный chat_id. Успешный ответ теперь:

```json
{
  "chat_id": "01900000-0000-7000-8000-000000000001",
  "generation_id": 42,
  "model_id": "cloudflare/flux-1-schnell",
  "model_name": "FLUX.1-schnell"
}
```

`image_url` удалён. `object_key` не возвращается ни здесь, ни в истории.
`GET /Text-to-Masterpiece/chats/{chat_id}` и `/chat_history` возвращают элементы
`id`, `prompt`, `created_at`, `model_id`, `model_name`; `id` — ID генерации.
Список чатов `/chats` не изменился.

### GET /images/{generation_id}

Проверяет владельца существующей генерации через общие JWT/guest зависимости и
DAO. Для чужой/отсутствующей генерации — одинаковый 404, до разрешения Storage и
любого запроса в B2. object_key берётся только из PostgreSQL. Транзакция чтения
закрывается до открытия B2 stream.

Ответ: исходный Content-Type, Content-Length при наличии, поток байтов,
`Cache-Control: private, no-store`, `X-Content-Type-Options: nosniff`.
Отсутствующий объект — 404, недоступность B2 до начала ответа — 503.
Локальный StaticFiles mount `/images` удалён.

### Авторизация браузера: важное согласование требований

Существующий проект хранит JWT в **HttpOnly cookie**, а не в JS. Поэтому React
использует существующий `credentials: include` и для пользователя, и для гостя.
Считать cookie в JavaScript и изготовить из неё Authorization невозможно без
ослабления HttpOnly или изменения auth-контрактов. Этого не сделано.

Общая backend-зависимость дополнительно принимает `Authorization: Bearer <JWT>`
для клиентов, которые уже имеют JWT. Нового token endpoint, хранения JWT в
localStorage/sessionStorage или выдачи токена JavaScript нет. Если браузер обязан
использовать именно Bearer-заголовок, отдельно потребуется согласовать изменение
текущего механизма выдачи/восстановления токена — это не часть данной интеграции.

### React

`getGenerationImage(id, signal)` получает Blob через API. `PrivateImage` создаёт
Blob URL, показывает loading/error/retry и освобождает URL при смене ID, владельца,
повторной попытке или unmount. Сигнал отмены и теги ID/владельца защищают от поздних
ответов предыдущего чата. Повторный render не скачивает тот же объект заново.

В Message и sessionStorage сохраняются только generationId, а не Blob URL или
ключ S3. Версия tab cache обновлена до v3. История, продолжение, New chat и перенос
гостевого чата используют тот же механизм. При входе/выходе изображение повторно
проверяется под текущим владельцем; старый Blob не показывается.

## Локальная проверка с настоящим B2

1. Создайте/проверьте **private** bucket. Обычный bucket-scoped Application Key
   должен разрешать readFiles/writeFiles/deleteFiles. Не используйте master key,
   не публикуйте credentials, не включайте SDK debug-логи с HTTP/signing данными.
2. Заполните `app/backend/.env` (существующие секреты и настройки БД/auth/лимитов
   сохраняются):

   ```dotenv
   B2_ENDPOINT=https://s3.UR-REGION.backblazeb2.com
   B2_REGION=UR-REGION
   B2_BUCKET_NAME=ttm-images
   B2_KEY_ID=<обычный Application Key ID>
   B2_APPLICATION_KEY=<Application Key>
   ```

   Endpoint/регион должны соответствовать вашему bucket. Текущий локальный `.env`
   уже содержит все поля из `.env.example`; реальные значения не менялись.
3. Миграция `object_key` уже выполнена — повторно ничего не мигрируйте.
   Из каталога `app`:

   ```sh
   (cd backend && uv sync --locked)
   backend/.venv/bin/uvicorn backend.main:app --host 127.0.0.1 --port 8080
   ```

4. В другом терминале:

   ```sh
   npm --prefix frontend ci
   VITE_API_URL=http://localhost:8080 npm --prefix frontend run dev
   ```

   Для локального HTTP нужны `COOKIE_SECURE=false`, `COOKIE_SAMESITE=lax`.
   Используйте одинаковое имя хоста (например, localhost) для frontend/backend.
   В production нужны HTTPS и корректные CORS/SameSite настройки вашего frontend.
   CORS самого B2 не нужен: браузер не обращается к B2 напрямую.
5. Отправьте prompt гостем, проверьте Blob-изображение и единственный объект
   `images/<uuid>.<extension>` с правильным Content-Type в B2. Это настоящий
   платный вызов Cloudflare/B2, в рамках настроенных лимитов.
6. Обновите страницу, продолжите чат, перезапустите backend и снова откройте чат.
   Существующие изображения должны загружаться без нового PUT.
7. Зарегистрируйте гостя/войдите: те же ID должны работать после переноса. После
   logout или из другой сессии запрос `/images/<старый-id>` должен дать 404.

Можно проверить скачивание через cookie jar:

```sh
curl -c /tmp/t2m-cookies.txt http://localhost:8080/Text-to-Masterpiece
curl -b /tmp/t2m-cookies.txt -c /tmp/t2m-cookies.txt \
  -H 'Content-Type: application/json' \
  -d '{"prompt":"A small red lighthouse","model_id":"cloudflare/flux-1-schnell"}' \
  http://localhost:8080/Text-to-Masterpiece/generate
# Подставьте generation_id из ответа:
curl -b /tmp/t2m-cookies.txt -D /tmp/t2m-image.headers \
  http://localhost:8080/images/42 -o /tmp/t2m-image
```

## Проверки

```sh
backend/.venv/bin/python -m pytest backend/tests -q
npm --prefix frontend test
npm --prefix frontend run lint
npm --prefix frontend run build
```

На момент реализации: **213 backend-тестов**, **43 frontend-теста**, lint и build.
Backend покрывает mock S3, MIME/key, права guest/user/Bearer, перенос при регистрации
и входе, потоковое чтение/закрытие, PUT/GET ошибки, rollback/delete, неизвестный
COMMIT и окончательный отказ COMMIT. PostgreSQL-тесты дополнительно проверяют,
что во время PUT нет транзакции, а отмена не освобождает locks раньше boto3 thread.
Frontend проверяет Blob, историю, auth-смену владельца, stale fetch, 401/404/503,
retry и revoke. Cloudflare и B2 в автоматических тестах не настоящие.

## Ограничения и эксплуатация

- Настоящие B2/Cloudflare вызовы в ходе автоматической проверки не выполнялись.
  Перед production проведите описанный smoke test, включая conditional PUT:
  endpoint должен поддерживать `If-None-Match: *`. При отсутствии поддержки
  намеренного fallback на небезопасную перезапись нет.
- Неопределённый PUT/COMMIT или авария между PUT и COMMIT могут оставить orphan.
  Автоматической фоновой сверки нет. После восстановления БД и завершения
  in-flight операций администратор должен проверить наличие object_key в
  `tests.users_requests` перед удалением. Ключи из логов нельзя удалять вслепую.
- B2 versioning/lifecycle/retention могут сохранять старые версии или запрещать
  delete. S3 delete текущего ключа не обещает физически стереть все версии.
  Настройка lifecycle и административная очистка версий остаются обязанностью
  оператора bucket.
- После начала streaming headers нельзя заменить 200 на JSON-ошибку. При сбое
  дальнейшего чтения поток закрывается, браузер получает ошибку загрузки и retry.
- 60 с — deadline Cloudflare, не всей последовательности PUT + PostgreSQL + cleanup.
  boto3 использует конечные socket timeouts; при отмене ждём worker, а не оставляем
  его незаметно работающим после освобождения слота. Жёсткое завершение процесса
  не может гарантировать остановку Cloudflare/S3 на удалённой стороне.
- Весь Blob находится в памяти браузера до выхода из чата. Очень длинные чаты с
  большими изображениями могут потребовать отдельной оптимизации/lazy loading.
- Если frontend развёрнут с CSP, разрешите `blob:` в img-src. Bucket остаётся
  private; доступность backend/БД/B2 нужна для новых скачиваний.

## Изменённые и добавленные файлы

Backend:

- `.env.example`, `core/config.py` — S3-настройки и SecretStr, без настоящих ключей.
- `services/image_storage.py` — заменён локальный storage, SDK/stream/cleanup.
- `api/images.py` — upload, сохранение ID, private GET, компенсация.
- `api/dependencies.py` — общая поддержка Bearer вместе с HttpOnly JWT.
- `database/queries.py`, `schemas.py` — object_key только внутри БД, generation_id в API.
- `main.py` — lifespan клиента, удаление StaticFiles.
- `tests/conftest.py`, `tests/test_image_storage.py` (новый),
  `tests/test_models_generation.py`, `tests/test_ai_budget_postgres.py`,
  `tests/test_auth_sessions.py`, `tests/test_chats.py`,
  `tests/test_generation_lock_postgres.py`, `tests/test_rate_limiting_postgres.py`.
- `README.md`, `B2_STORAGE.md` (новый) — документация и этот отчёт.

Frontend:

- `src/services/requests.ts`, `src/types/message.ts`, `src/utils/currentChat.ts`.
- `src/components/chat/PrivateImage.tsx` (новый), `src/components/chat/MessageList.tsx`.
- `src/pages/generate/GeneratePage.tsx`.
- `tests/private-images.test.mjs` (новый), `tests/models.test.mjs`, `tests/chats.test.mjs`.

Пользовательские изменения `database/models.py`, уже существующая миграция,
`tt.py` и добавление boto3 в `pyproject.toml` / `uv.lock` не перезаписывались.

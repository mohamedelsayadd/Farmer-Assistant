# Farmer Assistant — Chat API Contract

## `POST /api/v1/chat`

Sends one user turn to the farmer assistant and returns the assistant's text reply. Conversation history is kept server-side per `conversation_id`, so the client sends only the current message.

The endpoint accepts two request encodings:

| Content-Type | Use for |
|---|---|
| `application/json` | Text-only messages |
| `multipart/form-data` | Voice notes, plant images, or text + image |

Replies are always text (no audio is returned).

---

## 1. JSON request

```http
POST /api/v1/chat
Content-Type: application/json
```

```json
{
  "jwt": "<user ReNile JWT>",
  "conversation_id": "conv-123",
  "message": "إيه قراءات الحساسات بتاعتي النهارده؟"
}
```

| Field | Type | Required | Rules |
|---|---|---|---|
| `jwt` | string | yes | Non-empty. The user's ReNile token, used only to call ReNile on their behalf. |
| `conversation_id` | string | yes | Non-empty. Reuse the same value to continue a conversation. |
| `message` | string | yes | 1–7500 characters. |

---

## 2. Multipart request

```http
POST /api/v1/chat
Content-Type: multipart/form-data
```

| Field | Kind | Required | Rules |
|---|---|---|---|
| `jwt` | text | yes | Non-empty. |
| `conversation_id` | text | yes | Non-empty. |
| `message` | text | see below | 1–7500 characters. |
| `audio_file` | file | see below | Any audio format ffmpeg can decode (wav, mp3, m4a, ogg, webm, amr, …). Max size `ASR_MAX_AUDIO_BYTES` (default 10 MB). |
| `wav_file` | file | — | **Deprecated** alias of `audio_file`. |
| `image_file` | file | see below | Extension `.jpg`, `.jpeg`, `.png`, or `.webp`. Max size `PLANT_DISEASE_MAX_IMAGE_BYTES` (default 5 MB). |

Allowed combinations (at least one is required):

| Combination | Behavior |
|---|---|
| `message` | Same as a JSON request. |
| `audio_file` | The audio is transcribed and the transcript is used as the message. The transcript is returned in `transcript`. |
| `image_file` | The assistant diagnoses the plant image. |
| `message` + `image_file` | The assistant answers the message using the image. |

`audio_file` **cannot** be combined with `message` or `image_file`.

### Examples

```bash
# Voice note
curl -X POST http://localhost:8000/api/v1/chat \
  -F jwt="$JWT" -F conversation_id=conv-123 \
  -F audio_file=@question.m4a

# Plant image with a question
curl -X POST http://localhost:8000/api/v1/chat \
  -F jwt="$JWT" -F conversation_id=conv-123 \
  -F message="الورق ده فيه إيه؟" \
  -F image_file=@leaf.jpg
```

---

## 3. Response — `200 OK`

```json
{
  "conversation_id": "conv-123",
  "message": "النبات عنده لفحة متأخرة ...",
  "source": "tomato",
  "disease": "late_blight",
  "transcript": "الورق ده فيه إيه؟"
}
```

| Field | Type | Always present | Description |
|---|---|---|---|
| `conversation_id` | string | yes | Echo of the request's `conversation_id`. |
| `message` | string | yes | The assistant's reply (Arabic or English, matching the language the user typed). |
| `source` | string | no | Plant/crop identified by image diagnosis. Present only when an image was diagnosed. |
| `disease` | string | no | Disease identified by image diagnosis. Present only when an image was diagnosed. |
| `transcript` | string | no | Text transcribed from `audio_file`. Present only for voice requests. |

Optional fields are **omitted** (not `null`) when they don't apply.

### Degraded replies (still `200 OK`)

Temporary backend failures (LLM, Redis, tool errors) do not produce an error status; the reply `message` is a fixed Arabic text instead:

| Situation | `message` |
|---|---|
| LLM / memory / agent failure | `معلش، حصلت مشكلة مؤقتة. جرّب تاني بعد شوية.` |
| Assistant could not reach an answer | `معلش، مش قادر أوصل لإجابة واضحة دلوقتي.` |

---

## 4. Errors

Errors use FastAPI's standard shape:

```json
{ "detail": "audio_file cannot be sent with message or image_file." }
```

For field validation failures, `detail` is a list of Pydantic error objects instead of a string.

| Status | When | `detail` |
|---|---|---|
| `413` | Audio file larger than the limit | `audio_file is too large.` |
| `413` | Image file larger than the limit | `image_file is too large.` |
| `422` | JSON body is not valid JSON | `Request body must be valid JSON.` |
| `422` | JSON body is not an object | `Request body must be a JSON object.` |
| `422` | Missing/empty/too-long `jwt`, `conversation_id`, or `message` | List of validation errors |
| `422` | A text field was sent as a file | `<field> must be a text field.` |
| `422` | `audio_file` combined with `message` or `image_file` | `audio_file cannot be sent with message or image_file.` |
| `422` | Multipart request with no message, audio, or image | `Send message, audio_file, image_file, or message with image_file.` |
| `422` | Empty audio file | `audio_file must not be empty.` |
| `422` | Audio could not be decoded | `audio_file could not be decoded as audio.` |
| `422` | Transcription produced no text | `Audio transcription returned empty text.` |
| `422` | Unsupported image extension | `image_file must be one of: ['.jpeg', '.jpg', '.png', '.webp'].` |
| `422` | Empty image file | `image_file must not be empty.` |
| `503` | Speech-to-text service unavailable | `Audio transcription failed. Try again later.` |

# Farmer Assistant Chatbot API Documentation

This document describes only the chatbot API exposed by the Farmer Assistant backend.

## Base URL

Local development:

```text
http://localhost:8000
```

The Streamlit tester defaults to `CHAT_API_BASE_URL` when set, otherwise it uses its local default.

## Endpoint Summary

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/v1/chat` | Sends a user chat message, voice message, plant image, or plant image with text. |

## Authentication

The chatbot endpoint requires the client to send a ReNile JWT in the request body or form fields.

The JWT is used only by the backend when farm/device reading tools need to call ReNile APIs. It is not exposed to the LLM tools, prompts, Redis memory, or logs.

## Chat Endpoint

### `POST /api/v1/chat`

The endpoint supports two request content types:

| Content Type | Use Case |
|---|---|
| `application/json` | Text-only chat messages. |
| `multipart/form-data` | Text, voice, image, or text plus image messages. |

## JSON Text Request

Use JSON for text-only chat.

### Request Body

```json
{
  "jwt": "user-jwt",
  "conversation_id": "conversation-1",
  "message": "What are the latest readings?"
}
```

### Fields

| Field | Type | Required | Description |
|---|---|---:|---|
| `jwt` | string | Yes | ReNile user JWT. |
| `conversation_id` | string | Yes | Stable conversation ID used for chat memory. |
| `message` | string | Yes | User message, 1 to 7500 characters. |

### Example

```bash
curl -X POST http://localhost:8000/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{
    "jwt": "user-jwt",
    "conversation_id": "conversation-1",
    "message": "What are the latest readings?"
  }'
```

## Multipart Requests

Use `multipart/form-data` for voice and plant image messages.

### Common Fields

| Field | Type | Required | Description |
|---|---|---:|---|
| `jwt` | text | Yes | ReNile user JWT. |
| `conversation_id` | text | Yes | Stable conversation ID used for chat memory. |
| `message` | text | Conditional | Text message. Can be sent alone or with `image_file`. |
| `wav_file` | file | Conditional | WAV audio message. Must be sent alone. |
| `image_file` | file | Conditional | Plant image. Can be sent alone or with `message`. |

### Allowed Input Combinations

| Combination | Status |
|---|---|
| `message` only | Allowed |
| `image_file` only | Allowed |
| `message` + `image_file` | Allowed |
| `wav_file` only | Allowed |
| `wav_file` + `message` | Rejected |
| `wav_file` + `image_file` | Rejected |
| Empty request without `message`, `wav_file`, or `image_file` | Rejected |

## Multipart Text Request

```bash
curl -X POST http://localhost:8000/api/v1/chat \
  -F "jwt=user-jwt" \
  -F "conversation_id=conversation-1" \
  -F "message=إيه آخر القراءات؟"
```

## Voice Request

Voice requests must upload a WAV file with field name `wav_file`.

### Supported Audio

| Requirement | Value |
|---|---|
| Field name | `wav_file` |
| Format | WAV |
| Max size | Configured by `ASR_MAX_AUDIO_BYTES` |

### Example

```bash
curl -X POST http://localhost:8000/api/v1/chat \
  -F "jwt=user-jwt" \
  -F "conversation_id=conversation-1" \
  -F "wav_file=@voice.wav;type=audio/wav"
```

### Voice Flow

1. Backend validates the WAV upload.
2. Backend transcribes audio using the configured ASR provider.
3. Transcribed text is sent through the normal chatbot flow.
4. If enabled by request handling, the response can include generated WAV audio.

## Plant Image Request

Plant images must upload an image file with field name `image_file`.

### Supported Images

| Requirement | Value |
|---|---|
| Field name | `image_file` |
| Extensions | `.jpg`, `.jpeg`, `.png`, `.webp` |
| Max size | Configured by `PLANT_DISEASE_MAX_IMAGE_BYTES` |

### Image Only Example

```bash
curl -X POST http://localhost:8000/api/v1/chat \
  -F "jwt=user-jwt" \
  -F "conversation_id=conversation-1" \
  -F "image_file=@plant.jpg;type=image/jpeg"
```

### Text Plus Image Example

```bash
curl -X POST http://localhost:8000/api/v1/chat \
  -F "jwt=user-jwt" \
  -F "conversation_id=conversation-1" \
  -F "message=هل الورقة دي مصابة؟" \
  -F "image_file=@plant.jpg;type=image/jpeg"
```

### Plant Image Flow

1. Backend validates image type, size, and non-empty content.
2. Image bytes are kept internally and are not exposed to the LLM.
3. The LLM is told that the current request includes a plant image.
4. The LLM calls the backend tool `plant_diseases_detection`.
5. The backend tool calls the plant disease service:

```text
POST http://127.0.0.1:8002/api/v1/predict
```

The backend sends the uploaded image to that service using multipart field name `file`.

6. The plant disease result is returned to the LLM as tool output.
7. The LLM writes the final user-facing diagnosis.
8. Only the user text and assistant final answer are saved to Redis memory. Image bytes are not saved.

## Response

Successful requests return HTTP `200`.

### Response Body

```json
{
  "conversation_id": "conversation-1",
  "message": "Assistant response",
  "source": "yolo",
  "disease": "potato early blight",
  "audio_wav_base64": "UklGRg==",
  "audio_content_type": "audio/wav"
}
```

### Fields

| Field | Type | Nullable | Description |
|---|---|---:|---|
| `conversation_id` | string | No | Conversation ID from the request. |
| `message` | string | No | Final chatbot response. |
| `source` | string | Yes | Plant disease provider source such as `yolo`, `kindwise`, or `gemini`. Included only for plant image diagnosis when returned by the plant disease API. |
| `disease` | string | Yes | Disease name returned by the plant disease API. Included only for plant image diagnosis when a disease is detected. |
| `audio_wav_base64` | string | Yes | Base64 WAV response audio, when generated. |
| `audio_content_type` | string | Yes | Audio content type, usually `audio/wav`, when audio is generated. |

Normal text and farm reading responses usually omit `source`, `disease`, `audio_wav_base64`, and `audio_content_type`.

### Text Response Example

```json
{
  "conversation_id": "conversation-1",
  "message": "Here are the latest readings..."
}
```

### Plant Image Response Example

```json
{
  "conversation_id": "conversation-1",
  "message": "الصورة بتوضح احتمال إصابة النبات باللفحة المبكرة...",
  "source": "yolo",
  "disease": "potato early blight"
}
```

If the plant image API returns `source` but no disease, for example a healthy plant or unresolved diagnosis, the response can include `source` while omitting `disease`.

## Error Responses

### Invalid JSON

Status: `422 Unprocessable Entity`

```json
{
  "detail": "Request body must be valid JSON."
}
```

### Missing Input

Status: `422 Unprocessable Entity`

```json
{
  "detail": "Send message, wav_file, image_file, or message with image_file."
}
```

### Voice Sent With Text Or Image

Status: `422 Unprocessable Entity`

```json
{
  "detail": "wav_file cannot be sent with message or image_file."
}
```

### Unsupported Audio Type

Status: `422 Unprocessable Entity`

```json
{
  "detail": "wav_file must be a WAV audio file."
}
```

### Audio Too Large

Status: `413 Payload Too Large`

```json
{
  "detail": "wav_file is too large."
}
```

### Empty Audio

Status: `422 Unprocessable Entity`

```json
{
  "detail": "wav_file must not be empty."
}
```

### ASR Failure

Status: `503 Service Unavailable`

```json
{
  "detail": "Audio transcription failed. Try again later."
}
```

### Unsupported Image Type

Status: `422 Unprocessable Entity`

```json
{
  "detail": "image_file must be one of: ['.jpeg', '.jpg', '.png', '.webp']."
}
```

### Image Too Large

Status: `413 Payload Too Large`

```json
{
  "detail": "image_file is too large."
}
```

### Empty Image

Status: `422 Unprocessable Entity`

```json
{
  "detail": "image_file must not be empty."
}
```

## Client Notes

- Use `application/json` only for text-only messages.
- Use `multipart/form-data` for voice or image uploads.
- Send plant images to the chatbot backend as `image_file`; the chatbot backend forwards them to the plant disease API as `file`.
- `wav_file` must be sent alone.
- `image_file` can be sent alone or with `message`.
- Do not send Base64 images or audio JSON.
- Reuse the same `conversation_id` to continue a conversation.
- Use a new `conversation_id` to start a fresh conversation.

# FMS-Voice — API Contract

Arabic/English speech-to-text. Two endpoints, no auth, no versioning.

| | |
|---|---|
| **Local** | `http://192.168.0.4:5001` |
| **Public** | `https://41.32.195.157/asr` |
| **Languages** | `ar` (default), `en` |

---

## `POST /transcribe`

**Request** — `multipart/form-data`

| Field | Type | Required | Notes |
|---|---|---|---|
| `file` | file | yes | Any audio ffmpeg can decode: wav, mp3, m4a, ogg, opus, webm, flac, amr. Any sample rate, mono or stereo. Max 200 MB / 30 min. |
| `language` | string | no | `ar` or `en`. Defaults to `ar`. |

**Response** — `200 application/json`

```json
{
  "text": "ففي الحالة دي المسألة دي يعني more safe",
  "language": "ar",
  "duration_s": 3.56,
  "inference_s": 0.246,
  "rtfx": 14.47
}
```

| Field | Type | Meaning |
|---|---|---|
| `text` | string | The transcript. Empty string if no speech was found. |
| `language` | string | The language used (echoes the request). |
| `duration_s` | float | Length of the audio. |
| `inference_s` | float | Time spent in the model. |
| `rtfx` | float | `duration_s / inference_s`. Higher is faster. |

---

## `GET /health`

**Response** — `200` when ready, `503` while the model is loading.

```json
{
  "status": "ok",
  "model_id": "CohereLabs/cohere-transcribe-arabic-07-2026",
  "model_loaded": true,
  "device": "cuda:1",
  "gpu_name": "NVIDIA GeForce RTX 3090",
  "gpu_memory_used_mb": 19616,
  "gpu_memory_total_mb": 24124,
  "queue_depth": 0
}
```

---

## Errors

All errors return `{"detail": "<message>"}`.

| Code | Cause | What the caller should do |
|---|---|---|
| `400` | Empty file | Fix the upload |
| `413` | Over 200 MB or over 30 min | Split the audio |
| `415` | Not decodable as audio | Check the file |
| `422` | `language` not `ar`/`en` | Fix the parameter |
| `429` | More than 8 requests queued | Retry after a few seconds |
| `503` | Model loading, or GPU out of memory | Retry after a few seconds |

`429` and `503` are the only retryable codes. One request is processed at a time, so a long
file blocks the queue — expect to wait, and set a client timeout of 600s.

---

## Examples

```bash
curl -X POST http://192.168.0.4:5001/transcribe \
  -F "file=@recording.m4a" \
  -F "language=ar"
```

```python
import requests

with open("recording.m4a", "rb") as fh:
    r = requests.post(
        "http://192.168.0.4:5001/transcribe",
        files={"file": fh},
        data={"language": "ar"},
        timeout=600,
    )
r.raise_for_status()
text = r.json()["text"]
```

```javascript
const form = new FormData();
form.append("file", blob, "recording.webm");
form.append("language", "ar");

const res = await fetch("http://192.168.0.4:5001/transcribe", {
  method: "POST",
  body: form,
});
const { text } = await res.json();
```

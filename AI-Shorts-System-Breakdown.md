# AI YouTube Shorts Generator — Полный разбор системы

> Источник: https://github.com/SamurAIGPT/AI-Youtube-Shorts-Generator  
> Лицензия: MIT — можно использовать в коммерческих продуктах без ограничений

---

## Как это работает — большая картина

```
YouTube URL
    │
    ▼
[1] DOWNLOAD — yt-dlp скачивает видео в mp4
    │
    ▼
[2] TRANSCRIBE — faster-whisper транскрибирует аудио в текст с таймкодами
    │
    ▼
[3] CLASSIFY — LLM определяет тип контента (интервью / лекция / подкаст...)
    │
    ▼
[4] HIGHLIGHT RANKING — LLM анализирует транскрипт и находит вирусные моменты
    │                    возвращает JSON: [{start, end, score, title, hook, reason}]
    ▼
[5] DEDUPE — убираем перекрывающиеся клипы (>50% overlap → берём с высшим score)
    │
    ▼
[6] TOP-N SELECT — берём top N по score
    │
    ▼
[7] CROP — ffmpeg нарезает клипы, OpenCV делает вертикальное кадрирование с трекингом лица
    │
    ▼
short_01.mp4, short_02.mp4, short_03.mp4
```

---

## Стек технологий (local mode)

| Задача | Инструмент | Стоимость |
|--------|-----------|-----------|
| Скачивание видео | `yt-dlp` | Бесплатно |
| Транскрипция речи | `faster-whisper` (OpenAI Whisper, локально) | Бесплатно |
| Классификация контента | Gemini / OpenAI | ~$0.001 (маленький промпт) |
| Выбор хайлайтов | Gemini / OpenAI | ~$0.003–0.01 за видео |
| Нарезка видео | `ffmpeg` | Бесплатно |
| Вертикальное кадрирование | `opencv` (Haar cascade face tracking) | Бесплатно |

**Python зависимости:**
```
yt-dlp
faster-whisper
openai  (или google-genai для Gemini)
opencv-python
requests
python-dotenv
```

---

## САМОЕ ВАЖНОЕ — Промпты LLM

Вся магия в двух промптах в файле `shorts_generator/highlights.py`.

### Промпт 1: Классификация контента

```python
CONTENT_TYPE_PROMPT = """Analyze this video transcript sample and classify the content type.
Choose one: podcast, interview, tutorial, lecture, commentary, debate, vlog, other.
Also estimate content density: low (mostly filler/chit-chat), medium, or high (dense info/stories).
Respond with JSON only: {"content_type": "...", "density": "..."}"""
```

Этот промпт получает первые 25 сегментов транскрипта (~3000 символов) и возвращает тип.
Результат потом используется в основном промпте для тонкой настройки.

---

### Промпт 2: Критерии вирусности (КЛЮЧЕВОЙ)

```python
VIRALITY_CRITERIA = """
Virality signals to prioritize (ranked by impact):
1. HOOK MOMENTS — statements that create immediate curiosity
   ("The secret is...", "Nobody talks about...", "I was completely wrong about...")
2. EMOTIONAL PEAKS — genuine surprise, laughter, anger, vulnerability, excitement; raw unscripted reactions
3. OPINION BOMBS — strong, polarizing or counter-intuitive statements that trigger agree/disagree
4. REVELATION MOMENTS — surprising facts, stats, or confessions that reframe how the viewer thinks
5. CONFLICT/TENSION — disagreement, pushback, or a problem being confronted head-on
6. QUOTABLE ONE-LINERS — a sentence that works as a standalone quote card
7. STORY PEAKS — the climax or twist of an anecdote; the payoff moment
8. PRACTICAL VALUE — a concrete tip, hack, or insight the viewer can immediately apply
"""
```

### Промпт 3: Системный промпт для ранжирования (MAIN SYSTEM PROMPT)

```python
HIGHLIGHT_SYSTEM_PROMPT = """You are an elite short-form video editor who has studied thousands
of viral clips on TikTok, Instagram Reels, and YouTube Shorts.
You know exactly what makes viewers stop scrolling, watch to the end, and share.

{virality_criteria}

Content type: {content_type} | Density: {density}

Your task: identify the most viral-worthy highlights from the transcript.

Rules:
- Every highlight must open with a strong HOOK — a line that grabs attention within the first 3 seconds
- Duration sweet spot: 45-90 seconds.
  Go shorter (20-44s) only for a perfect standalone one-liner.
  Go longer (91-180s) only when a story arc needs full context to land
- Never cut mid-sentence or mid-thought — each clip must feel complete and self-contained
- Clips must not overlap significantly with each other
- Score 0-100 on viral potential (not general quality)
- Generate at least {min_clips} highlights
- For each highlight, identify the single best "hook_sentence" — the opening line
- Explain in one sentence why this clip is viral ("virality_reason")

Respond ONLY with valid JSON (no markdown, no explanation):
{"highlights":[{"title":"string","start_time":float,"end_time":float,"score":int,
"hook_sentence":"string","virality_reason":"string"}]}"""
```

**Этот промпт + транскрипт с таймкодами** = вся логика выбора клипов.

---

## Как формируется транскрипт для LLM

Каждый сегмент Whisper превращается в строку вида:
```
[12.5s] And that is when I realized everything I knew was wrong.
[18.2s] Nobody in the room said a word.
[21.0s] The silence lasted almost a minute.
```

Это дает LLM точные временные метки для определения start_time / end_time клипов.

---

## Алгоритм дедупликации

```python
def dedupe_highlights(highlights):
    # Сортируем по score (убывание)
    highlights = sorted(highlights, key=lambda x: int(x.get("score", 0)), reverse=True)
    kept = []
    for h in highlights:
        h_dur = h["end_time"] - h["start_time"]
        # Проверяем overlap с уже принятыми клипами
        overlapping = False
        for k in kept:
            overlap = min(h["end_time"], k["end_time"]) - max(h["start_time"], k["start_time"])
            if overlap > 0 and overlap > 0.5 * h_dur:  # >50% overlap → выбрасываем
                overlapping = True
                break
        if not overlapping:
            kept.append(h)
    return kept
```

---

## Логика кадрирования (Face Tracking)

В `local/clipper.py` — двухшаговый процесс:

**Шаг 1 — ffmpeg нарезка:**
```bash
ffmpeg -i source.mp4 -ss {start} -to {end} -c:v libx264 -preset fast -crf 20 -c:a aac clip.mp4
```

**Шаг 2 — OpenCV вертикальное кадрирование:**
1. Открываем клип кадр за кадром
2. Ищем лица через Haar Cascade (`haarcascade_frontalface_default.xml`)
3. Берём самое большое лицо (говорящий) как центр кадра
4. Применяем **smoothing = 0.15** — камера плавно следует за лицом, не дёргается
5. Если лицо не найдено — центрируем по горизонтали
6. Сохраняем кадрированное видео, затем мержим обратно с аудио через ffmpeg

```python
smoothing = 0.15  # насколько агрессивно преследуем новую позицию лица
# При каждом кадре:
new_cx = int(last_cx + (detected_cx - last_cx) * smoothing)
```

---

## Обработка длинных видео (>30 минут)

```python
LONG_VIDEO_THRESHOLD = 1800   # секунд (30 мин)
CHUNK_SIZE_SECONDS = 1200      # 20-минутные куски
CHUNK_OVERLAP_SECONDS = 60     # 1 минута overlap между кусками
```

Видео длиннее 30 минут разбивается на 20-минутные куски с перекрытием 1 минуту,
чтобы не потерять хайлайты на границах. Таймкоды корректируются обратно к исходному видео.

---

## Структура ответа LLM

LLM возвращает чистый JSON:
```json
{
  "highlights": [
    {
      "title": "Getting Fired from Apple",
      "start_time": 366.2,
      "end_time": 447.8,
      "score": 95,
      "hook_sentence": "And then I got fired. How can you get fired from a company you started?",
      "virality_reason": "Personal vulnerability + absurdist hook triggers immediate curiosity and sympathy"
    }
  ]
}
```

---

## Как встроить в свой продукт

### Вариант 1 — Использовать как Python-библиотеку

```python
from shorts_generator import generate_shorts

result = generate_shorts(
    youtube_url="https://www.youtube.com/watch?v=...",
    num_clips=5,
    aspect_ratio="9:16",
    mode="local",   # "local" или "api"
)

for short in result["shorts"]:
    print(f"Score: {short['score']}")
    print(f"Title: {short['title']}")
    print(f"Hook: {short['hook_sentence']}")
    print(f"File: {short['clip_url']}")
    print(f"Why viral: {short['virality_reason']}")
```

### Вариант 2 — Взять только промпты и логику

Если нужно встроить только выбор хайлайтов (без видео), минимальный код:

```python
import json
from google import genai

client = genai.Client(api_key="YOUR_KEY")

def find_highlights(transcript_segments: list, num_clips: int = 3) -> list:
    # Формируем текст транскрипта с таймкодами
    transcript_text = "\n".join(
        f"[{s['start']:.1f}s] {s['text'].strip()}"
        for s in transcript_segments
    )
    
    prompt = f"""You are an elite short-form video editor...
    
    {VIRALITY_CRITERIA}
    
    Find {num_clips * 2} most viral moments. Return JSON only:
    {{"highlights":[{{"title":"...","start_time":0.0,"end_time":0.0,"score":0,"hook_sentence":"...","virality_reason":"..."}}]}}
    
    Transcript:
    {transcript_text}"""
    
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
        config={"response_mime_type": "application/json"}
    )
    
    data = json.loads(response.text)
    return sorted(data["highlights"], key=lambda x: x["score"], reverse=True)[:num_clips]
```

### Вариант 3 — Только кадрирование (без выбора хайлайтов)

```python
# Из local/clipper.py — можно взять функцию целиком
crop_clip_local(
    source_path="video.mp4",
    start_time=124.3,
    end_time=187.6,
    aspect_ratio="9:16",
    out_path="short.mp4"
)
```

---

## Конфигурируемые параметры

В `highlights.py` — изменяют поведение алгоритма:

```python
CHUNK_SIZE_SECONDS = 1200       # размер куска для длинных видео
LONG_VIDEO_THRESHOLD = 1800     # порог "длинного видео"
CHUNK_OVERLAP_SECONDS = 60      # перекрытие между кусками
GPT_CALL_TIMEOUT_SECONDS = 300  # таймаут LLM вызова
```

В `VIRALITY_CRITERIA` — можно добавить/убрать/переставить критерии вирусности.
Например, для образовательного контента поднять "PRACTICAL VALUE" на первое место.

---

## .env конфигурация

```env
# Local mode (рекомендуется)
LLM_PROVIDER=gemini              # или openai
GEMINI_API_KEY=your_key
GEMINI_MODEL=gemini-2.5-flash    # модель для LLM вызовов
LOCAL_WHISPER_MODEL=base         # tiny/base/small/medium/large-v3 (чем больше, тем точнее)
LOCAL_WHISPER_DEVICE=auto        # auto/cpu/cuda
LOCAL_OUTPUT_DIR=output          # куда сохранять клипы

# API mode (через MuAPI — платно, но без локальных зависимостей)
MUAPI_API_KEY=your_muapi_key
```

---

## Что можно улучшить в своём продукте

1. **Субтитры** — транскрипт уже есть в SRT формате, можно прожечь на видео через ffmpeg
2. **B-roll** — по ключевым словам из хайлайта искать стоковые видео через Pexels/Pixabay API
3. **Музыка** — добавить фоновый трек в нарезанный клип
4. **Превью** — генерировать thumbnail из первого кадра клипа
5. **Батч** — обрабатывать несколько видео параллельно через `concurrent.futures`
6. **Whisper large-v3** — вместо `base` для лучшего качества транскрипции (в 5–7x медленнее)
7. **Claude** — заменить Gemini на Claude Sonnet/Haiku для highlight ranking (часто лучше следует JSON schema)

---

## Реальные затраты (оценка)

| Видео | Длина | Whisper (local) | LLM | Итого |
|-------|-------|-----------------|-----|-------|
| Короткое | 5 мин | бесплатно | ~$0.001 | ~$0.001 |
| Среднее | 20 мин | бесплатно | ~$0.005 | ~$0.005 |
| Длинное | 1 час | бесплатно | ~$0.015 | ~$0.015 |

С Gemini free tier: **1500 видео/день бесплатно** (если не упирается в дневной лимит).

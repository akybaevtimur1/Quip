/**
 * Programmatic SEO landing pages ("use-case" pages) — BILINGUAL.
 *
 * WHY: one landing page can't rank for every query — search engines rank a *page*
 * per intent, not a site. So each high-intent query cluster gets its own real page
 * with a unique H1, copy, steps, benefits and FAQ. This is the layer that makes
 * "typed «turn long video into shorts» → found our app" actually work.
 *
 * BILINGUAL (option B, 2026-06-19): the Russian-speaking market is Yandex ≈ 73% /
 * Google ≈ 26%, but Google's English index is the bigger long-tail prize. So every
 * use-case carries BOTH languages under the SAME slug:
 *   - EN (default, for Google): /use-case/<slug>      → `en` content
 *   - RU (for Yandex):          /ru/use-case/<slug>   → `ru` content
 * The two URLs are tied together with hreflang (en / ru / x-default) so each engine
 * serves the right language. These are NOT thin doorway pages: each carries
 * substantive, unique content per language so Google/Yandex treat them as useful.
 *
 * To add a page: append an entry here with both `en` and `ru`. sitemap.ts,
 * generateStaticParams and BOTH routes (EN + RU) pick it up automatically. Keep copy
 * honest and mapped to the real product (explainable clips: hook + confidence score +
 * a plain reason it works; flash-free 9:16 reframe; burned-in captions; credit
 * pricing — see lib/plans.ts).
 *
 * Full semantic core / keyword research lives in docs/SEO_STRATEGY.md.
 */

export type Locale = "en" | "ru";

export interface UseCaseStep {
  title: string;
  body: string;
}

export interface UseCaseBenefit {
  title: string;
  body: string;
}

export interface UseCaseFaqItem {
  q: string;
  a: string;
}

/** Per-language content for one use-case page. */
export interface UseCaseContent {
  /** <title> — keep ≤ 60 chars where possible, keyword near the front. */
  title: string;
  /** <meta description> — ≤ ~155 chars, includes the keyword, sells the click. */
  metaDescription: string;
  /** Visible H1. */
  h1: string;
  /** Lead paragraph under the H1. */
  intro: string;
  /** "How it works" / "Как это работает" — 3 steps. */
  steps: UseCaseStep[];
  /** "Why Quip" / "Почему Quip" — 3 benefits specific to this use case. */
  benefits: UseCaseBenefit[];
  /** Unique FAQ → rendered + emitted as FAQPage JSON-LD. */
  faq: UseCaseFaqItem[];
  /** Closing CTA headline. */
  ctaTitle: string;
}

export interface UseCase {
  /** URL slug → /use-case/<slug> (EN) and /ru/use-case/<slug> (RU). Same slug both langs. */
  slug: string;
  /** Primary keyword (English) this page targets — for our own reference / docs. */
  keyword: string;
  /** English content (default route, Google). */
  en: UseCaseContent;
  /** Russian content (/ru route, Yandex). */
  ru: UseCaseContent;
}

export const USE_CASES: UseCase[] = [
  {
    slug: "make-shorts",
    keyword: "turn long videos into shorts",
    en: {
      title: "Turn Long Videos Into Shorts, Automatically | Quip",
      metaDescription:
        "Turn long videos and podcasts into short vertical clips automatically. Quip finds the strong moments, reframes to 9:16, adds captions, and tells you why each clip will land. 2 free videos.",
      h1: "Turn long videos into shorts — automatically",
      intro:
        "Upload a long video or podcast and Quip finds the moments worth posting, reframes them to vertical 9:16, writes a hook, and tells you in plain language why each short will land. Not thirty random clips to sift through — a handful you can actually post with confidence.",
      steps: [
        {
          title: "Upload your source",
          body: "A file or a link: podcast, interview, stream, webinar, or lecture, up to 3 hours. The more talking, the stronger the moments.",
        },
        {
          title: "Quip finds and explains",
          body: "It transcribes, picks the best segments, writes a hook, assigns a confidence score, and explains in plain words why each moment works.",
        },
        {
          title: "Polish and publish",
          body: "A smooth 9:16 frame that tracks the speaker, burned-in captions, your style. Export and post with a reason — not a guess.",
        },
      ],
      benefits: [
        {
          title: "Explainable shorts",
          body: "Every clip comes with a hook, a confidence score, and a reason — so you post deliberately, not blindly.",
        },
        {
          title: "Flash-free reframe",
          body: "A steady 9:16 reframe keeps the speaker in frame. No jumping crop box, no flicker, no throwaway frames.",
        },
        {
          title: "Honest pricing",
          body: "One credit = one video. No token casino, no surprise paywall. Start free with 2 videos every month.",
        },
      ],
      faq: [
        {
          q: "How many shorts will I get from one video?",
          a: "A handful of strong clips, not a pile to sift through. Each comes with a confidence score so you can pick the best ones to post.",
        },
        {
          q: "Do I need to know how to edit?",
          a: "No. Clipping, the 9:16 reframe, and captions are automatic. The editor is there if you want to tweak the text or style.",
        },
        {
          q: "Is it free?",
          a: "Yes — 2 videos every month with no card, which is 120 minutes of source. Paid plans drop the watermark and unlock 1080p export.",
        },
        {
          q: "What kind of video works best?",
          a: "Talking content: podcasts, interviews, webinars, streams, lectures. Quip works from speech, so more dialogue means stronger moments.",
        },
      ],
      ctaTitle: "Make your first shorts free",
    },
    ru: {
      title: "Создание шортсов из видео — автоматически | Quip",
      metaDescription:
        "Автоматическое создание шортсов из длинных видео и подкастов. Quip находит сильные моменты, режет в 9:16, добавляет субтитры и объясняет, почему клип сработает. 2 видео бесплатно.",
      h1: "Создание шортсов из видео — на автомате",
      intro:
        "Загрузите длинное видео или подкаст — Quip сам найдёт моменты, которые стоит постить, нарежет их в вертикальный формат 9:16, подберёт хук и подскажет, почему каждый шортс выстрелит. Не просто «тридцать клипов на разбор», а несколько готовых, в которых вы уверены.",
      steps: [
        {
          title: "Загрузите исходник",
          body: "Файл или ссылка: подкаст, интервью, стрим, вебинар или лекция — до 3 часов. Чем больше речи, тем сильнее моменты.",
        },
        {
          title: "Quip находит и объясняет",
          body: "Транскрибирует, выбирает лучшие фрагменты, пишет хук, ставит оценку уверенности и объясняет простыми словами, почему момент зайдёт.",
        },
        {
          title: "Доработайте и публикуйте",
          body: "Плавный кадр 9:16, который следует за спикером, сочные субтитры, ваш стиль. Экспорт — и в ленту с пониманием, а не на удачу.",
        },
      ],
      benefits: [
        {
          title: "Объяснимые шортсы",
          body: "Каждый клип идёт с хуком, оценкой уверенности и причиной — вы постите осознанно, а не вслепую.",
        },
        {
          title: "Кадрирование без миганий",
          body: "Ровный рефрейм 9:16 держит спикера в кадре. Никаких прыгающих рамок и кадров-мусора.",
        },
        {
          title: "Честная цена",
          body: "Кредит = одно видео. Никаких токенов и скрытых пейволлов. Старт — 2 видео в месяц бесплатно.",
        },
      ],
      faq: [
        {
          q: "Сколько шортсов получится из одного видео?",
          a: "Quip отдаёт несколько сильных клипов, а не вал на разбор. Каждый — с оценкой уверенности, чтобы вы выбрали лучшие для публикации.",
        },
        {
          q: "Нужно ли уметь монтировать?",
          a: "Нет. Нарезка, кадр 9:16 и субтитры делаются автоматически. В редакторе можно поправить текст и стиль, если хочется.",
        },
        {
          q: "Это бесплатно?",
          a: "Да, на старте 2 видео в месяц без карты — это 120 минут исходника. На платных планах нет вотермарка и доступен экспорт 1080p.",
        },
      ],
      ctaTitle: "Соберите первые шортсы бесплатно",
    },
  },
  {
    slug: "podcast-to-shorts",
    keyword: "podcast to shorts",
    en: {
      title: "Podcast to Shorts: Auto-Clip Your Episodes | Quip",
      metaDescription:
        "Turn a podcast into short vertical clips automatically. Quip pulls the best moments from your episode, adds captions, and explains why each clip works. Free to start.",
      h1: "Podcast to shorts, the easy way",
      intro:
        "A one-hour episode becomes ready-to-post vertical clips in minutes. Quip listens to the conversation, finds the most compelling moments, reframes them to 9:16, and tells you why that exact segment is worth posting.",
      steps: [
        {
          title: "Upload the episode",
          body: "Audio or video of a podcast, interview, or talk show, up to 3 hours. Quip works from speech, so conversation-heavy content is ideal.",
        },
        {
          title: "Quip picks the moments",
          body: "It transcribes, finds complete thoughts and punchlines, writes a hook, and scores each clip's confidence.",
        },
        {
          title: "Export for Reels, Shorts, TikTok",
          body: "Vertical frame tracking the speaker, captions in your style, no watermark on paid plans.",
        },
      ],
      benefits: [
        {
          title: "Cuts on meaning, not a timer",
          body: "Clips start and end on thought boundaries, so nothing cuts off mid-sentence. The conversation stays intact.",
        },
        {
          title: "A reason for every clip",
          body: "You see why a moment is strong: the hook, the moment type, and a confidence score. Fewer clips, more hits.",
        },
        {
          title: "Fast enough for a weekly show",
          body: "One episode becomes a week of clips — no timeline scrubbing, no manual editing.",
        },
      ],
      faq: [
        {
          q: "Which podcasts work best?",
          a: "Conversational ones: interviews, chats, panels. The more natural speech there is, the more accurately Quip finds strong moments.",
        },
        {
          q: "Can I upload audio only?",
          a: "Quip works from the speech track, but a vertical clip needs visuals. For audio-only shows, upload a recording with the speaker on camera.",
        },
        {
          q: "Which languages are supported?",
          a: "English and Russian work today, with language detected automatically — no setting to flip.",
        },
        {
          q: "How long does it take?",
          a: "Usually minutes, depending on episode length. You can watch the status in the dashboard while it processes.",
        },
      ],
      ctaTitle: "Clip your episode into shorts",
    },
    ru: {
      title: "Нарезка подкастов на шортсы и клипы | Quip",
      metaDescription:
        "Автоматическая нарезка подкастов на короткие вертикальные клипы. Quip выделяет лучшие моменты эпизода, добавляет субтитры и объясняет, почему фрагмент сработает.",
      h1: "Нарезка подкастов на шортсы",
      intro:
        "Эпизод на час превращается в готовые вертикальные клипы за пару минут. Quip слушает разговор, находит самые цепляющие моменты, режет их в 9:16 и объясняет, почему именно этот фрагмент стоит выложить.",
      steps: [
        {
          title: "Загрузите эпизод",
          body: "Аудио или видео подкаста, интервью или разговорного шоу — до 3 часов. Quip работает по речи, так что говорящий контент идеален.",
        },
        {
          title: "Quip выбирает моменты",
          body: "Транскрибирует, находит законченные мысли и панчи, пишет хук и ставит оценку уверенности по каждому клипу.",
        },
        {
          title: "Экспорт под Reels, Shorts, TikTok",
          body: "Вертикальный кадр за спикером, субтитры в вашем стиле, без вотермарка на платных планах.",
        },
      ],
      benefits: [
        {
          title: "Понимает разговор",
          body: "Режет по смыслу — на границах мыслей, а не по таймеру. Клип не обрывается на полуслове.",
        },
        {
          title: "Причина для каждого клипа",
          body: "Видно, почему момент сильный: хук, тип момента и оценка уверенности. Меньше клипов — больше попаданий.",
        },
        {
          title: "Быстро для еженедельного выпуска",
          body: "Один эпизод → пачка клипов на неделю контента. Без монтажа и скрабинга таймлайна.",
        },
      ],
      faq: [
        {
          q: "Какие подкасты подходят лучше всего?",
          a: "Разговорные: интервью, беседы, дискуссии. Чем больше живой речи, тем точнее Quip находит сильные моменты.",
        },
        {
          q: "Можно загрузить только аудио?",
          a: "Quip работает по дорожке речи; для вертикального видео нужен видеоряд. Для чисто аудио лучше загрузить запись со спикером в кадре.",
        },
        {
          q: "Поддерживается русский язык?",
          a: "Да. Язык определяется автоматически — русский и английский работают уже сейчас.",
        },
      ],
      ctaTitle: "Нарежьте свой эпизод на клипы",
    },
  },
  {
    slug: "make-reels",
    keyword: "make instagram reels from video",
    en: {
      title: "Make Instagram Reels From Long Video | Quip",
      metaDescription:
        "Make Instagram Reels from long videos automatically. Quip finds the moments, reframes to vertical 9:16, adds captions, and explains why each Reel will land. Start free.",
      h1: "Make Reels from your videos",
      intro:
        "Turn an interview, podcast, or stream into ready-to-post Reels. Quip picks the moments that hold attention, reframes them to 9:16, and adds captions — and tells you why each Reel earns a spot in the feed.",
      steps: [
        {
          title: "Upload a long video",
          body: "Podcast, interview, webinar, stream — Quip finds the Reel-worthy moments inside it.",
        },
        {
          title: "Get vertical clips",
          body: "Strong moments in 9:16, each with a hook, captions, and a confidence score.",
        },
        {
          title: "Publish to Reels",
          body: "1080p export with no watermark on paid plans — post straight from the file.",
        },
      ],
      benefits: [
        {
          title: "Built for Instagram",
          body: "Vertical 9:16, a frame that tracks the speaker, and readable burned-in captions — exactly what the feed rewards.",
        },
        {
          title: "A hook in the first second",
          body: "Quip suggests an opening hook so viewers stop scrolling instead of swiping past.",
        },
        {
          title: "You know what to post",
          body: "The confidence score and reason help you pick the Reels that are actually worth publishing.",
        },
      ],
      faq: [
        {
          q: "How is this better than editing Reels by hand?",
          a: "Quip handles finding the moments, the reframe, and the captions, and tells you which clip is strongest. You save hours and post deliberately.",
        },
        {
          q: "Can I choose a caption style?",
          a: "Yes. The editor has several caption styles and hook presets so you can match your visual identity.",
        },
        {
          q: "Which aspect ratios are available?",
          a: "9:16 for Reels, plus 1:1, 4:5, and 16:9 on paid plans — for any placement.",
        },
      ],
      ctaTitle: "Make Reels from your video",
    },
    ru: {
      title: "Создание Reels из видео автоматически | Quip",
      metaDescription:
        "Создание Reels для Instagram из длинных видео. Quip находит моменты, режет в вертикаль 9:16, добавляет субтитры и объясняет, почему рилс зайдёт. Старт бесплатно.",
      h1: "Создание Reels из ваших видео",
      intro:
        "Превратите интервью, подкаст или стрим в готовые Reels. Quip сам выбирает моменты, которые держат внимание, кадрирует в 9:16 и добавляет субтитры — а ещё объясняет, почему каждый рилс достоин ленты.",
      steps: [
        {
          title: "Загрузите длинное видео",
          body: "Подкаст, интервью, вебинар, стрим — Quip найдёт в нём материал для рилсов.",
        },
        {
          title: "Получите вертикальные клипы",
          body: "Сильные моменты в 9:16 с хуком, субтитрами и оценкой уверенности по каждому.",
        },
        {
          title: "Опубликуйте в Reels",
          body: "Экспорт 1080p без вотермарка на платных планах — выкладывайте сразу.",
        },
      ],
      benefits: [
        {
          title: "Формат под Instagram",
          body: "Вертикаль 9:16, динамичный кадр за спикером и читаемые субтитры — ровно то, что любит лента.",
        },
        {
          title: "Хук в первой секунде",
          body: "Quip предлагает зацепку для старта рилса, чтобы зритель не пролистнул.",
        },
        {
          title: "Понятно, что постить",
          body: "Оценка уверенности и причина помогают выбрать рилсы, которые реально стоят публикации.",
        },
      ],
      faq: [
        {
          q: "Чем это лучше ручного монтажа Reels?",
          a: "Quip берёт на себя поиск моментов, кадрирование и субтитры и подсказывает, какой клип сильнее. Вы экономите часы и постите осознанно.",
        },
        {
          q: "Можно выбрать стиль субтитров?",
          a: "Да. В редакторе доступны разные стили субтитров и пресеты хуков — подгоните под свой визуал.",
        },
        {
          q: "Какие соотношения сторон есть?",
          a: "9:16 для Reels, а также 1:1, 4:5 и 16:9 на платных планах — под любую площадку.",
        },
      ],
      ctaTitle: "Сделайте Reels из своего видео",
    },
  },
  {
    slug: "horizontal-to-vertical",
    keyword: "horizontal to vertical video",
    en: {
      title: "Horizontal to Vertical Video (16:9 to 9:16) | Quip",
      metaDescription:
        "Convert horizontal 16:9 video to vertical 9:16. Quip reframes with speaker tracking — no flicker, no jumping crop box. Plus auto captions and moment clipping.",
      h1: "Horizontal to vertical video",
      intro:
        "Shot in 16:9 but need 9:16? Quip converts horizontal video to vertical, keeping the speaker centered in frame — smoothly, with no jitter and no throwaway frames. It clips the strong moments and adds captions along the way.",
      steps: [
        {
          title: "Upload the horizontal source",
          body: "Any 16:9 video: interview, podcast, webinar, or meeting recording.",
        },
        {
          title: "Quip reframes to 9:16",
          body: "The frame follows the speaker along a fixed grid, with no shaking. The result is a clean vertical.",
        },
        {
          title: "Take the finished clips",
          body: "Vertical clips with captions and a hook, ready to publish.",
        },
      ],
      benefits: [
        {
          title: "Flicker-free reframe",
          body: "The frame is locked to the video's grid — no jumping crop box and no shimmer on transitions.",
        },
        {
          title: "The speaker stays in frame",
          body: "Speaker tracking, not a static center crop. The face never drifts off the edge.",
        },
        {
          title: "More than a crop",
          body: "You also get moment clipping, captions, and a reason each clip is worth posting.",
        },
      ],
      faq: [
        {
          q: "Will the speaker drift out of frame?",
          a: "No. The frame follows the speaker and keeps them centered in the vertical. The movement is smooth, with no jerks.",
        },
        {
          q: "Will there be flicker on transitions?",
          a: "No. The reframe is built on a frame-grid invariant, so the crop doesn't twitch or shimmer.",
        },
        {
          q: "What if there are several people on camera?",
          a: "Quip follows the active speaker. You can nudge the frame position by hand in the editor.",
        },
      ],
      ctaTitle: "Convert your video to vertical",
    },
    ru: {
      title: "Вертикальные видео из горизонтальных 9:16 | Quip",
      metaDescription:
        "Переделайте горизонтальное видео 16:9 в вертикальное 9:16. Quip кадрирует с слежением за спикером — без миганий и прыгающих рамок. Плюс субтитры и нарезка моментов.",
      h1: "Вертикальные видео из горизонтальных",
      intro:
        "Снято в 16:9, а нужно в 9:16? Quip переводит горизонтальное видео в вертикальный формат, удерживая спикера в центре кадра — плавно, без рывков и кадров-мусора. Заодно нарезает сильные моменты и добавляет субтитры.",
      steps: [
        {
          title: "Загрузите горизонтальный исходник",
          body: "Любое видео 16:9: интервью, подкаст, вебинар, запись со встречи.",
        },
        {
          title: "Quip кадрирует в 9:16",
          body: "Кадр следует за говорящим по сетке, без дрожания. Результат — аккуратная вертикаль.",
        },
        {
          title: "Заберите готовые клипы",
          body: "Вертикальные клипы с субтитрами и хуком, готовые к публикации.",
        },
      ],
      benefits: [
        {
          title: "Рефрейм без миганий",
          body: "Кадр держится строго по сетке кадров — никаких прыгающих рамок и мерцания на переходах.",
        },
        {
          title: "Спикер всегда в кадре",
          body: "Слежение за говорящим, а не статичная обрезка по центру. Лицо не уезжает за край.",
        },
        {
          title: "Не только кадр",
          body: "Заодно — нарезка моментов, субтитры и причина, почему клип сработает.",
        },
      ],
      faq: [
        {
          q: "Спикер не будет уезжать из кадра?",
          a: "Нет. Кадр следует за говорящим, удерживая его в центре вертикали. Движение плавное, без рывков.",
        },
        {
          q: "Будут ли мигания на переходах?",
          a: "Нет. Рефрейм построен по инварианту кадровой сетки — кадр не дёргается и не мерцает.",
        },
        {
          q: "А если в кадре несколько людей?",
          a: "Quip ориентируется на активного спикера. В редакторе можно поправить положение кадра вручную.",
        },
      ],
      ctaTitle: "Переведите видео в вертикаль",
    },
  },
  {
    slug: "youtube-to-shorts",
    keyword: "youtube to shorts",
    en: {
      title: "YouTube to Shorts: Clip Long Videos | Quip",
      metaDescription:
        "Turn a long YouTube video into Shorts. Quip pulls the best moments, reframes to 9:16, adds captions, and explains why each Short will land. 2 free videos.",
      h1: "YouTube to Shorts",
      intro:
        "A long YouTube video is a stack of ready-made Shorts. Quip finds the strongest moments, reframes them to vertical, adds captions, and tells you which Short to post first.",
      steps: [
        {
          title: "Upload the video",
          body: "A long YouTube video: podcast, review, interview, or stream — up to 3 hours of source.",
        },
        {
          title: "Quip builds the Shorts",
          body: "It picks the moments, writes a hook, scores confidence, and reframes to 9:16.",
        },
        {
          title: "Publish to Shorts",
          body: "Vertical clips with captions, 1080p export with no watermark on paid plans.",
        },
      ],
      benefits: [
        {
          title: "Long becomes short",
          body: "One video feeds a week of Shorts — with no manual editing.",
        },
        {
          title: "Moments that hold",
          body: "Quip looks for complete, compelling segments, not random chunks cut on a timer.",
        },
        {
          title: "A clear choice",
          body: "The confidence score and reason show which Shorts to publish first.",
        },
      ],
      faq: [
        {
          q: "Which YouTube videos work?",
          a: "Talking content: podcasts, interviews, reviews, streams, lectures. The more speech, the more strong moments.",
        },
        {
          q: "Do I have to edit anything by hand?",
          a: "No. Clipping, the frame, and captions are automatic. The editor is only there if you want to tweak details.",
        },
        {
          q: "Is the quality preserved?",
          a: "Yes — paid plans export at 1080p with no watermark. The free plan is 720p with a small watermark.",
        },
      ],
      ctaTitle: "Make Shorts from your video",
    },
    ru: {
      title: "Шортсы из YouTube-видео автоматически | Quip",
      metaDescription:
        "Сделайте Shorts из длинного YouTube-видео. Quip выделяет лучшие моменты, режет в 9:16, добавляет субтитры и объясняет, почему шортс сработает. 2 видео бесплатно.",
      h1: "Шортсы из YouTube-видео",
      intro:
        "Длинный ролик на YouTube — это десятки готовых Shorts. Quip находит самые сильные моменты, кадрирует их в вертикаль, добавляет субтитры и подсказывает, какой шортс стоит выложить первым.",
      steps: [
        {
          title: "Загрузите ролик",
          body: "Длинное YouTube-видео: подкаст, обзор, интервью, стрим — до 3 часов исходника.",
        },
        {
          title: "Quip собирает Shorts",
          body: "Выбирает моменты, пишет хук, ставит оценку уверенности и режет в формат 9:16.",
        },
        {
          title: "Публикуйте в Shorts",
          body: "Вертикальные клипы с субтитрами, экспорт 1080p без вотермарка на платных планах.",
        },
      ],
      benefits: [
        {
          title: "Длинное → короткое",
          body: "Один ролик кормит ленту Shorts на неделю вперёд — без ручного монтажа.",
        },
        {
          title: "Моменты, которые держат",
          body: "Quip ищет законченные цепляющие фрагменты, а не случайные куски по таймеру.",
        },
        {
          title: "Понятный выбор",
          body: "Оценка уверенности и причина показывают, какие шортсы публиковать в первую очередь.",
        },
      ],
      faq: [
        {
          q: "Какие YouTube-видео подходят?",
          a: "Говорящий контент: подкасты, интервью, обзоры, стримы, лекции. Чем больше речи, тем больше сильных моментов.",
        },
        {
          q: "Нужно ли что-то монтировать вручную?",
          a: "Нет. Нарезка, кадр и субтитры — автоматически. Редактор нужен только если хотите подправить детали.",
        },
        {
          q: "Сохраняется ли качество?",
          a: "Да, на платных планах экспорт в 1080p без вотермарка. На бесплатном — 720p с небольшим вотермарком.",
        },
      ],
      ctaTitle: "Соберите Shorts из своего ролика",
    },
  },
  {
    slug: "video-to-clips",
    keyword: "long video to short clips",
    en: {
      title: "Long Video to Short Clips, Automatically | Quip",
      metaDescription:
        "Cut a long video into short clips automatically. Quip finds the strong moments, cuts on meaning, reframes to 9:16, and adds captions. No manual editing.",
      h1: "Long video to short clips",
      intro:
        "An hour of footage is dozens of short clips. Quip cuts long video on meaning, not a timer: it finds complete, strong moments, reframes them to vertical, and adds captions. All that's left is picking the best ones.",
      steps: [
        {
          title: "Upload the recording",
          body: "Podcast, webinar, interview, stream, or lecture — up to 3 hours of source.",
        },
        {
          title: "Quip cuts on meaning",
          body: "It detects thought boundaries, picks the strong segments, and assigns a confidence score.",
        },
        {
          title: "Take the clips",
          body: "Finished vertical clips with a hook and captions — for Shorts, Reels, and TikTok.",
        },
      ],
      benefits: [
        {
          title: "Cuts on meaning",
          body: "Clips begin and end on thought boundaries instead of cutting off mid-sentence.",
        },
        {
          title: "Less noise",
          body: "A few strong clips with a reason, instead of a pile you have to sift through by hand.",
        },
        {
          title: "All in one pass",
          body: "Clipping, the 9:16 reframe, captions, and a hook — in a single run, with no separate tools.",
        },
      ],
      faq: [
        {
          q: "How are the moments chosen?",
          a: "Quip looks for complete, compelling segments and rates them with a confidence score, so you can see which clips are strongest.",
        },
        {
          q: "What's the maximum source length?",
          a: "Up to 3 hours per video. Length is limited only by the minutes left on your plan.",
        },
        {
          q: "Can I adjust a clip's boundaries?",
          a: "Yes — the editor lets you tweak the timing, the text, and the caption style.",
        },
      ],
      ctaTitle: "Cut your video into clips",
    },
    ru: {
      title: "Нарезка длинного видео на короткие клипы | Quip",
      metaDescription:
        "Автоматическая нарезка длинного видео на короткие клипы. Quip находит сильные моменты, режет по смыслу, кадрирует в 9:16 и добавляет субтитры. Без ручного монтажа.",
      h1: "Нарезка длинного видео на клипы",
      intro:
        "Час записи — это десятки коротких клипов. Quip режет длинное видео по смыслу, а не по таймеру: находит законченные сильные моменты, кадрирует в вертикаль и добавляет субтитры. Вам остаётся выбрать лучшие.",
      steps: [
        {
          title: "Загрузите запись",
          body: "Подкаст, вебинар, интервью, стрим, лекция — до 3 часов исходника.",
        },
        {
          title: "Quip режет по смыслу",
          body: "Определяет границы мыслей, выбирает сильные фрагменты и ставит оценку уверенности.",
        },
        {
          title: "Заберите клипы",
          body: "Готовые вертикальные клипы с хуком и субтитрами — под Shorts, Reels и TikTok.",
        },
      ],
      benefits: [
        {
          title: "Резка по смыслу",
          body: "Клипы начинаются и заканчиваются на границах мыслей, а не обрываются на полуслове.",
        },
        {
          title: "Меньше шума",
          body: "Несколько сильных клипов с причиной вместо вала, который надо разбирать вручную.",
        },
        {
          title: "Всё в одном проходе",
          body: "Нарезка, кадр 9:16, субтитры и хук — за один запуск, без отдельных инструментов.",
        },
      ],
      faq: [
        {
          q: "По какому принципу выбираются моменты?",
          a: "Quip ищет законченные, цепляющие фрагменты и оценивает их уверенностью, чтобы вы видели, какие клипы сильнее.",
        },
        {
          q: "Какая максимальная длина исходника?",
          a: "До 3 часов на одно видео. Длина ограничена только остатком минут на вашем плане.",
        },
        {
          q: "Можно поправить границы клипа?",
          a: "Да, в редакторе можно подправить тайминги, текст и стиль субтитров.",
        },
      ],
      ctaTitle: "Нарежьте своё видео на клипы",
    },
  },
  {
    slug: "auto-subtitles",
    keyword: "auto subtitles / automatic captions",
    en: {
      title: "Auto Subtitles & Automatic Captions for Video | Quip",
      metaDescription:
        "Add subtitles to video automatically. Quip transcribes speech, syncs captions word by word, and burns them in your chosen style — for shorts, Reels, and TikTok.",
      h1: "Auto subtitles for your video",
      intro:
        "Captions hold the viewer who's watching with the sound off. Quip transcribes the speech, syncs the captions word by word, and burns them into the video in your chosen style — and clips the strong moments to vertical along the way.",
      steps: [
        {
          title: "Upload the video",
          body: "A podcast, interview, or any talking video — Quip transcribes the speech automatically.",
        },
        {
          title: "Get synced captions",
          body: "Captions appear word by word, exactly in time with the speech, in the style you choose.",
        },
        {
          title: "Export the clip",
          body: "The captions are burned into the video — publish straight away, no separate editor needed.",
        },
      ],
      benefits: [
        {
          title: "Word-by-word sync",
          body: "Captions land in time with the speech instead of drifting — the clip looks professional.",
        },
        {
          title: "Styles and presets",
          body: "Several caption styles and hook presets so you can match your visual identity.",
        },
        {
          title: "English and Russian",
          body: "Language is detected automatically; English and Russian both work today.",
        },
      ],
      faq: [
        {
          q: "How accurate are the captions?",
          a: "Quip uses solid speech recognition with word-level sync. Any word can be corrected in the editor.",
        },
        {
          q: "Can I change the caption style and size?",
          a: "Yes. Several caption styles are available; color, position, and hook are tunable to your brand.",
        },
        {
          q: "Are the captions burned into the video?",
          a: "Yes — they're burned into the exported clip, so there's no separate subtitle file to manage.",
        },
      ],
      ctaTitle: "Add captions to your video",
    },
    ru: {
      title: "Автоматические субтитры на видео | Quip",
      metaDescription:
        "Добавьте субтитры на видео автоматически. Quip распознаёт речь, синхронизирует подписи по словам и оформляет в выбранном стиле — для шортсов, Reels и TikTok.",
      h1: "Автоматические субтитры на видео",
      intro:
        "Субтитры удерживают зрителя, который смотрит без звука. Quip распознаёт речь, синхронизирует подписи по словам и вшивает их в видео в выбранном стиле — а заодно нарезает сильные моменты в вертикальный формат.",
      steps: [
        {
          title: "Загрузите видео",
          body: "Подкаст, интервью или любой говорящий ролик — Quip распознает речь автоматически.",
        },
        {
          title: "Получите синхронные субтитры",
          body: "Подписи появляются по словам, точно в такт речи, в выбранном стиле.",
        },
        {
          title: "Экспортируйте клип",
          body: "Субтитры вшиты в видео — публикуйте сразу, без отдельного редактора.",
        },
      ],
      benefits: [
        {
          title: "Синхронизация по словам",
          body: "Подписи идут точно в такт, а не плывут от речи — клип смотрится профессионально.",
        },
        {
          title: "Стили и пресеты",
          body: "Несколько стилей субтитров и пресетов хуков — подгоните под свой визуал.",
        },
        {
          title: "Русский и английский",
          body: "Язык определяется автоматически; русский и английский работают уже сейчас.",
        },
      ],
      faq: [
        {
          q: "Насколько точны субтитры?",
          a: "Quip использует качественное распознавание речи и синхронизацию по словам. Любое слово можно поправить в редакторе.",
        },
        {
          q: "Можно изменить стиль и размер подписей?",
          a: "Да. Доступны разные стили субтитров; цвет, положение и хук настраиваются под ваш бренд.",
        },
        {
          q: "Субтитры вшиваются в видео?",
          a: "Да, подписи прожигаются в экспортируемый клип — отдельный файл субтитров не нужен.",
        },
      ],
      ctaTitle: "Добавьте субтитры к своему видео",
    },
  },
  {
    slug: "webinar-to-shorts",
    keyword: "webinar to clips",
    en: {
      title: "Webinar to Clips: Repurpose Your Recording | Quip",
      metaDescription:
        "Turn a webinar or interview into short clips. Quip pulls the key moments, reframes to 9:16, adds captions, and explains why each segment works. Free to start.",
      h1: "Webinar and interview to clips",
      intro:
        "A one-hour webinar or interview is a ready supply of content. Quip finds the key points and strongest answers, cuts them into vertical clips with captions, and tells you which segments are worth posting.",
      steps: [
        {
          title: "Upload the recording",
          body: "Webinar, interview, panel, or Q&A — up to 3 hours of source.",
        },
        {
          title: "Quip finds the key parts",
          body: "It surfaces the main points and strong answers, writes a hook, and scores each clip's confidence.",
        },
        {
          title: "Take the vertical clips",
          body: "A 9:16 frame tracking the speaker, captions in your style — for social and promo.",
        },
      ],
      benefits: [
        {
          title: "Content for promo",
          body: "Short clips from a webinar promote your next session and product — no separate shoot required.",
        },
        {
          title: "Key points up front",
          body: "Quip pulls out the most valuable segments, so you don't have to re-watch the whole hour by hand.",
        },
        {
          title: "Ready to publish",
          body: "The frame, captions, and hook are already in place — just pick and post.",
        },
      ],
      faq: [
        {
          q: "Does a recording with two speakers work?",
          a: "Yes. Quip follows the active speaker and keeps them in frame; you can adjust the position in the editor.",
        },
        {
          q: "Can I make clips for different platforms?",
          a: "Yes — beyond 9:16, paid plans add 1:1, 4:5, and 16:9 for YouTube, Instagram, and LinkedIn.",
        },
        {
          q: "How long does processing take?",
          a: "Usually minutes, depending on the recording length. The status is visible in the dashboard while it processes.",
        },
      ],
      ctaTitle: "Make clips from your webinar",
    },
    ru: {
      title: "Клипы из вебинаров и интервью | Quip",
      metaDescription:
        "Сделайте короткие клипы из вебинара или интервью. Quip выделяет ключевые моменты, режет в 9:16, добавляет субтитры и объясняет, почему фрагмент сработает.",
      h1: "Клипы из вебинаров и интервью",
      intro:
        "Часовой вебинар или интервью — это готовый запас контента. Quip находит ключевые мысли и сильные ответы, режет их в вертикальные клипы с субтитрами и подсказывает, какие фрагменты стоит выложить.",
      steps: [
        {
          title: "Загрузите запись",
          body: "Вебинар, интервью, панель или Q&A — до 3 часов исходника.",
        },
        {
          title: "Quip находит ключевое",
          body: "Выделяет тезисы и сильные ответы, пишет хук и оценивает уверенность по каждому клипу.",
        },
        {
          title: "Заберите вертикальные клипы",
          body: "Кадр 9:16 за спикером, субтитры в вашем стиле — под соцсети и промо.",
        },
      ],
      benefits: [
        {
          title: "Контент для промо",
          body: "Короткие клипы из вебинара продвигают следующий эфир и продукт без отдельной съёмки.",
        },
        {
          title: "Ключевые мысли наверх",
          body: "Quip вытаскивает самые ценные фрагменты, чтобы не пересматривать весь час вручную.",
        },
        {
          title: "Готово к публикации",
          body: "Кадр, субтитры и хук уже на месте — остаётся выбрать и выложить.",
        },
      ],
      faq: [
        {
          q: "Подойдёт запись с двумя спикерами?",
          a: "Да. Quip ориентируется на активного говорящего и удерживает его в кадре; положение можно поправить в редакторе.",
        },
        {
          q: "Можно ли сделать клипы на разные площадки?",
          a: "Да, помимо 9:16 доступны 1:1, 4:5 и 16:9 на платных планах — под YouTube, Instagram и LinkedIn.",
        },
        {
          q: "Сколько времени занимает обработка?",
          a: "Обычно минуты, в зависимости от длины записи. Статус виден в дашборде во время обработки.",
        },
      ],
      ctaTitle: "Сделайте клипы из своего вебинара",
    },
  },
];

/** Lookup by slug (used by both routes + generateMetadata). */
export function getUseCase(slug: string): UseCase | undefined {
  return USE_CASES.find((u) => u.slug === slug);
}

/** Get the locale-specific content block for a use-case. */
export function getUseCaseContent(useCase: UseCase, locale: Locale): UseCaseContent {
  return locale === "ru" ? useCase.ru : useCase.en;
}

/**
 * Canonical path for a use-case in a given locale. EN is the default (root); RU lives
 * under /ru. NB: NOT named with a `use` prefix on purpose — eslint's
 * react-hooks/rules-of-hooks treats any `use*` identifier as a React Hook.
 */
export function localeUseCasePath(slug: string, locale: Locale): string {
  return locale === "ru" ? `/ru/use-case/${slug}` : `/use-case/${slug}`;
}

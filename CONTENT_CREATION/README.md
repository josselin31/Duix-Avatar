# CONTENT_CREATION workflow

## One-command pipeline (recommended)

Run everything for one markdown brief:

```bash
python CONTENT_CREATION/run_md_pipeline.py --source 1.md
```

This single command will:

1. Generate the perfect prompt package from reverse-prompt embeddings
2. Run text-to-video using configured provider (`sora`, `duix`, or `storyboard`)
3. Generate voice-over with OpenAI TTS
4. Produce final rendered video in `GENERATED`

Expected outputs are grouped per brief:

- `CONTENT_CREATION/GENERATED/1/1.md` (source copy)
- `CONTENT_CREATION/GENERATED/1/1.rendered.mp4` (main output)
- `CONTENT_CREATION/GENERATED/1/artifacts/1.perfect_prompt.md`
- `CONTENT_CREATION/GENERATED/1/artifacts/1.duix_narration.txt`
- `CONTENT_CREATION/GENERATED/1/artifacts/1.context_ranking.json`
- `CONTENT_CREATION/GENERATED/1/artifacts/1.openai_tts.wav`
- `CONTENT_CREATION/GENERATED/1/artifacts/1.pipeline_checklist.md`
- `CONTENT_CREATION/GENERATED/1/artifacts/1.render_test_report.md` (only when provider `duix` is used)

Defaults tuned to avoid overload:

- `DUIX_AUTO_START_SERVICES="0"` (no heavy Docker auto-start)
- `MAX_RENDER_SECONDS="18"` (caps fallback output duration)
- `TEXT_TO_VIDEO_PROVIDER="sora"` (true text-to-video when available)

## 1) Write simple briefs

Drop your simple prompt briefs as markdown files in `CONTENT_CREATION/`, for example:

- `CONTENT_CREATION/1.md`
- `CONTENT_CREATION/2.md`

## 2) Build "perfect prompts" with reverse-context embeddings

Generate for a single file:

```bash
python CONTENT_CREATION/embed_and_build_prompt.py --source 1.md
```

Generate for all markdown files in `CONTENT_CREATION/`:

```bash
python CONTENT_CREATION/embed_and_build_prompt.py --all
```

Outputs are written to:

- `CONTENT_CREATION/GENERATED/<stem>/artifacts/<stem>.perfect_prompt.md`
- `CONTENT_CREATION/GENERATED/<stem>/artifacts/<stem>.duix_narration.txt`
- `CONTENT_CREATION/GENERATED/<stem>/artifacts/<stem>.context_ranking.json`

## 3) Run a Duix render test

```bash
python CONTENT_CREATION/render_video_test.py --source-stem 1
```

Output:

- `CONTENT_CREATION/GENERATED/<stem>/artifacts/<stem>.render_test_report.md`

If all Duix services and model variables are configured, a rendered video is copied to:

- `CONTENT_CREATION/GENERATED/<stem>/<stem>.rendered.mp4`

## 4) Required settings

The script reads `.env` in repo root:

- `OPENAI_API_KEY`
- `OPENAI_PROMPT_MODEL` (optional, default `gpt-4.1`)
- `OPENAI_EMBEDDING_MODEL` (optional, default `text-embedding-3-large`)
- `OPENAI_TTS_MODEL` (optional, default `gpt-4o-mini-tts`)
- `OPENAI_TTS_VOICE` (optional, default `nova`)
- `REVERSE_CONTEXT_TOP_K` (optional, default `5`)

For automated Duix render tests, also configure `DUIX_*` variables documented in `.env`.
For Sora video generation, configure:

- `OPENAI_VIDEO_MODEL` (default `sora-2`)
- `OPENAI_VIDEO_SECONDS` (allowed `4`, `8`, `12`)
- `OPENAI_VIDEO_SIZE` (default `720x1280`)

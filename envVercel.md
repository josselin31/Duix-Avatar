## Vercel environment variables (project root: `vercel-web`)

### Required

- `OPENAI_API_KEY`  
  OpenAI API key with access to video models (Sora).

- `BLOB_READ_WRITE_TOKEN`  
  Token from Vercel Blob (Storage tab).

### Recommended

- `OPENAI_VIDEO_MODEL=sora-2`
- `OPENAI_VIDEO_SECONDS=12`  
  Allowed values: `4`, `8`, `12`.
- `OPENAI_VIDEO_SIZE=720x1280`  
  Recommended for iPhone vertical output.
- `JOBS_RETENTION_HOURS=24`
- `CRON_SECRET=<random-long-secret>`

### Optional

- `NEXT_PUBLIC_APP_NAME=Glyce Video Studio`

## Notes

- The cron route `/api/cron/cleanup` runs every hour (defined in `vercel-web/vercel.json`).
- Any generated job older than 24h is deleted (md/json/video blobs).

# Vercel Web App

Phone-first web UI to:

1. paste text
2. convert it to `.md`
3. generate `.mp4`
4. keep history for 24h
5. auto-delete old videos via cron

## Deploy on Vercel

1. Import this repository in Vercel.
2. Set **Root Directory** to `vercel-web`.
3. Add environment variables from `../envVercel.md`.
4. Deploy.

## Local dev

```bash
cd vercel-web
npm install
npm run dev
```

Open [http://localhost:3000](http://localhost:3000).

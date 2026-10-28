# Job tracker (free, runs on GitHub Actions)

Every morning at 08:00 IST a GitHub-hosted runner pulls listings from 37 sources,
applies your hard filters, optionally asks Gemini (free tier) to rank the survivors,
and sends you a digest on Telegram (and/or email). Nothing runs on your laptop.

## Setup (about 15 minutes, all free)

1. **Create a GitHub repo** (public gives unlimited Actions minutes; private gives 2,000/month, still plenty).
   Upload this whole folder. Note: `data/seen.json` is committed by the bot, so if the repo is
   public, your seen-job list is public too (it holds only hashes, not your details).
2. **Telegram bot**: message `@BotFather`, send `/newbot`, copy the token.
   Send any message to your new bot, then open
   `https://api.telegram.org/bot<TOKEN>/getUpdates` and copy `chat.id`.
3. **Add repo secrets** (Settings > Secrets and variables > Actions > New repository secret):

   | Secret | Needed? | Where to get it |
   |---|---|---|
   | `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` | recommended | step 2 |
   | `GEMINI_API_KEY` | optional (smarter ranking) | aistudio.google.com/apikey |
   | `RELIEFWEB_APPNAME` | optional | request at reliefweb.int/help/api |
   | `ADZUNA_APP_ID`, `ADZUNA_APP_KEY` | optional | developer.adzuna.com |
   | `JOOBLE_API_KEY` | optional | jooble.org/api/about |
   | `SMTP_USER`, `SMTP_PASS`, `EMAIL_TO` | optional email | Gmail app password |

   Sources whose key is missing are skipped and listed in the digest footer.
4. **Run the health check first**: Actions tab > job-tracker > Run workflow > mode `doctor`.
   Open the run's log: every source shows `ok`, `empty`, `error` or `skipped`.
5. **Fix what is not ok**, then run with mode `run`. After that it runs daily by itself.

## Reading the doctor output

- `ok`: returned listings.
- `empty`: reachable but nothing found. For `page` sources this usually means the site builds its job list
  with JavaScript. Look for the site's own RSS feed or job board on Greenhouse/Lever/Ashby and switch the
  source type, or set `enabled: false`.
- `error`: wrong board name, blocked, or site changed. The message says which.
- `skipped`: missing optional key.

## Tuning (everything is in `config/config.yaml`)

- `profile.include_title_any`, `exclude_title_any`: title keywords and dealbreakers (whole-word match).
- `profile.locations_any`, `allow_remote`, `remote_exclude_any`: where you would work.
- `profile.unknown_location`: `keep` (NGO pages rarely state one) or `drop`.
- `llm.min_score`: raise to 7 or 8 if the digest is noisy.
- `max_digest`: jobs per day; extras wait until tomorrow.
- Add a company: copy a `greenhouse` / `lever` / `ashby` line and change `board`.
  The board name is the last part of the company's careers URL
  (`boards.greenhouse.io/<board>`, `jobs.lever.co/<board>`, `jobs.ashbyhq.com/<board>`).

## Local test (optional, light)

    pip install -r requirements.txt pytest
    python -m pytest -q
    PYTHONPATH=src python -m jobtracker run --dry-run --no-llm

## Notes

- LinkedIn, Indeed and Naukri are deliberately not scraped: they block it and it breaks their terms.
  Adzuna and Jooble cover much of the Indian market through their free APIs.
- If every source fails the run exits non-zero, so GitHub emails you a failed-run notice.

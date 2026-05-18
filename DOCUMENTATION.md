---

#### REDIS — Upstash (Free)

| Variable | Example Value | Why We Need It |
|---|---|---|
| `REDIS_URL` | `rediss://default:xxx@xxx.upstash.io:6379` | Powers our event bus and JWT revocation list |

**Why Redis?**
Two critical jobs in our app:
- Real-time events: when teacher creates assignment, Redis 
  instantly notifies all student dashboards (pub/sub)
- JWT revocation: when a user logs out, we store their 
  token ID in Redis so it can't be reused

**Why Upstash?**
Free managed Redis. 10,000 commands/day free.
Works from anywhere — no config change between local and production.

**How to get it:**
1. Go to upstash.com → sign up (free, no credit card)
2. Click "Create Database"
3. Name: `classroom-redis`
4. Type: Regional
5. Region: AP South (closest to India)
6. Click Create
7. On the database page, scroll to "REST API" section
8. Copy the `REDIS_URL` value (starts with `rediss://`)

**Note:** The `rediss://` (with double s) means SSL encrypted.
Always use this, never plain `redis://` in production.

---

#### LLM — Groq (Free Tier)

| Variable | Example Value | Why We Need It |
|---|---|---|
| `LLM_PROVIDER` | `groq` | Tells app which AI provider to use |
| `GROQ_API_KEY` | `gsk_xxxx` | Authenticates our requests to Groq |

**Why Groq?**
Free tier. Extremely fast inference (tokens per second).
Runs open source models like Llama 3.3 and Mixtral.

**Why different models per agent?**
We assign heavier models to complex tasks and lighter 
models to simple tasks. This optimises speed and cost:

| Variable | Model | Why This Model |
|---|---|---|
| `MODEL_ROUTER` | `llama-3.1-8b-instant` | Simple classification, needs to be fast |
| `MODEL_SAFETY` | `llama-3.1-8b-instant` | Simple filtering, needs to be fast |
| `MODEL_TEACHER` | `llama-3.3-70b-versatile` | Complex reasoning for assignment creation |
| `MODEL_STUDENT` | `llama-3.3-70b-versatile` | Understanding varied student submissions |
| `MODEL_SUMMARISER` | `mixtral-8x7b-32768` | Long context window for cohort summaries |
| `MODEL_REMINDER` | `gemma2-9b-it` | Simple nudge generation, lightweight |
| `MODEL_PARENT` | `mixtral-8x7b-32768` | Long context for weekly digest generation |

**How to get GROQ_API_KEY:**
1. Go to console.groq.com → sign up
2. Click "API Keys" in left sidebar
3. Click "Create API Key"
4. Name it `classroom-companion`
5. Copy the key immediately — it won't be shown again

---

#### TELEGRAM

| Variable | Example Value | Why We Need It |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | `7234567890:AAF-xxx` | Authenticates our bot with Telegram |
| `TELEGRAM_WEBHOOK_SECRET` | `rahul_classroom_2026_xK9` | Verifies webhook requests are genuinely from Telegram |

**Why a webhook secret?**
When Telegram sends us a message, anyone on the internet 
could theoretically send a fake request to our webhook URL.
The secret is a password only Telegram knows — we check it 
on every incoming request. If it's missing or wrong, we 
reject the request immediately.

**How to get TELEGRAM_BOT_TOKEN:**
1. Open Telegram → search @BotFather
2. Send `/newbot`
3. Enter bot name: `Classroom Companion`
4. Enter username: `classroom_companion_bot` (must be unique, 
   add your name if taken)
5. BotFather replies with your token
6. Copy it — keep it secret

**How to set TELEGRAM_WEBHOOK_SECRET:**
You create this yourself. Requirements:
- At least 20 characters
- Mix of letters and numbers
- No spaces
```bash
# Generate one:
python -c "import secrets; print(secrets.token_urlsafe(24))"
```

---

#### TWILIO WHATSAPP

| Variable | Example Value | Why We Need It |
|---|---|---|
| `TWILIO_ACCOUNT_SID` | `ACfb3bea...` | Identifies your Twilio account |
| `TWILIO_AUTH_TOKEN` | `abc123...` | Password for Twilio API calls |
| `TWILIO_WHATSAPP_NUMBER` | `whatsapp:+14155238886` | The sandbox number messages come from |

**Why Twilio?**
WhatsApp does not allow direct API access without 
Meta Business verification (takes weeks). Twilio provides 
a sandbox that works immediately for testing.

**The $15.50 trial credit is enough for our demo.**

**How to get credentials:**
1. Go to twilio.com → log in
2. On the main dashboard you will see:
   - Account SID: visible directly (starts with AC...)
   - Auth Token: click the eye icon to reveal
3. Copy both values
4. WhatsApp number is always `whatsapp:+14155238886` 
   for the sandbox — no need to look this up

---

#### AUTH — JWT Keys

| Variable | Example Value | Why We Need It |
|---|---|---|
| `MAGIC_LINK_TTL_MINUTES` | `15` | How long a magic login link is valid |
| `JWT_ALGORITHM` | `RS256` | Asymmetric signing algorithm (more secure than HS256) |
| `JWT_ACCESS_TTL_MINUTES` | `60` | How long before access token expires |
| `JWT_REFRESH_TTL_DAYS` | `7` | How long before refresh token expires |
| `JWT_PRIVATE_KEY` | `-----BEGIN RSA...` | Signs JWT tokens (keep secret) |
| `JWT_PUBLIC_KEY` | `-----BEGIN PUBLIC...` | Verifies JWT tokens (can be shared) |

**Why asymmetric keys (RS256)?**
With symmetric keys (HS256), anyone with the key can both 
create AND verify tokens — risky if the key leaks.
With asymmetric keys, the private key signs tokens 
(only our server) and the public key verifies them 
(can be shared safely). More secure for production systems.

**How to generate JWT keys:**
We have a script for this. Run it after setup:
```bash
python scripts/generate_keys.py
```
It will print your private and public keys.
Copy each one into your .env on a single line 
(the script formats them correctly).

---

#### SUPABASE STORAGE

| Variable | Example Value | Why We Need It |
|---|---|---|
| `SUPABASE_URL` | `https://xxxx.supabase.co` | Base URL for Supabase API calls |
| `SUPABASE_ANON_KEY` | `eyJxxx...` | Public key for Supabase client |
| `UPLOAD_BUCKET` | `submissions` | Name of the storage bucket for files |

**Why Supabase Storage?**
Students can submit files and voice notes. 
We need somewhere to store them. Supabase gives 1GB free 
and it's already part of our Supabase project —
no new service needed.

**How to get SUPABASE_URL and SUPABASE_ANON_KEY:**
1. Go to your Supabase project dashboard
2. Click Settings (gear icon, bottom left sidebar)
3. Click "API" in the settings menu
4. You will see two values:
   - Project URL → this is your `SUPABASE_URL`
   - anon / public key → this is your `SUPABASE_ANON_KEY`

**UPLOAD_BUCKET** — leave as `submissions`. 
We create this bucket ourselves when we run setup.

---

#### REMINDER POLICY

| Variable | Default | Why We Need It |
|---|---|---|
| `MAX_NUDGES_PER_DAY` | `2` | Max reminders per student per day |
| `QUIET_HOURS_START` | `22` | No reminders after 10pm |
| `QUIET_HOURS_END` | `8` | No reminders before 8am |
| `ESCALATION_THRESHOLD` | `3` | Miss 3 reminders → parent gets alerted |

These are default values. Admin can override them 
per school tenant from the admin console.

---

### ROTATING SECRETS (For Juniors)

If a secret is ever exposed or compromised:

**Rotating SECRET_KEY:**
```bash
python -c "import secrets; print(secrets.token_hex(32))"
```
Update in .env → restart server.
Note: existing sessions will be invalidated.

**Rotating JWT Keys:**
```bash
python scripts/generate_keys.py
```
Update JWT_PRIVATE_KEY and JWT_PUBLIC_KEY in .env.
All existing JWT tokens will be immediately invalid.
Users will need to log in again.

**Rotating GROQ_API_KEY:**
1. Go to console.groq.com → API Keys
2. Delete the old key
3. Create a new key
4. Update GROQ_API_KEY in .env → restart server

**Rotating TELEGRAM_BOT_TOKEN:**
1. Open @BotFather → send /mybots
2. Select your bot → API Token → Revoke current token
3. Copy new token → update in .env → restart server

**Rotating TWILIO credentials:**
1. Log in to twilio.com
2. Go to Account → API keys
3. Create new key, revoke old one
4. Update in .env → restart server

---

### PRODUCTION CHECKLIST

Before deploying to Railway, make sure:
- [ ] `DEBUG=false`
- [ ] `APP_ENV=production`
- [ ] `ALLOWED_ORIGINS` set to your Railway URL only
- [ ] `FRONTEND_URL` set to your Railway URL
- [ ] All keys are production keys (not test/sandbox)
- [ ] JWT keys are freshly generated
- [ ] `SECRET_KEY` is freshly generated
- [ ] No placeholder values remaining
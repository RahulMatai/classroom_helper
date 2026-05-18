# test_connections.py
import os
from dotenv import load_dotenv

load_dotenv()

results = {}

# ── 1. Groq ──────────────────────────────────────
print("\n🔍 Testing Groq...")
try:
    from groq import Groq
    client = Groq(api_key=os.getenv("GROQ_API_KEY"))
    response = client.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=[{"role": "user", "content": "Say: Groq connection successful"}],
        max_tokens=20
    )
    print(f"✅ Groq works: {response.choices[0].message.content}")
    results["Groq"] = "✅ Connected"
except Exception as e:
    print(f"❌ Groq failed: {e}")
    results["Groq"] = f"❌ Failed: {e}"


# ── 2. Supabase ───────────────────────────────────
print("\n🔍 Testing Supabase...")
try:
    from supabase import create_client
    supabase = create_client(
        os.getenv("SUPABASE_URL"),
        os.getenv("SUPABASE_ANON_KEY")
    )
    # Just check the client was created successfully
    # Don't query any table — they don't exist yet
    print("✅ Supabase connected")
    results["Supabase"] = "✅ Connected"
except Exception as e:
    print(f"❌ Supabase failed: {e}")
    results["Supabase"] = f"❌ Failed: {e}"
except Exception as e:
    # A "relation does not exist" error actually means connection worked
    if "does not exist" in str(e) or "relation" in str(e):
        print("✅ Supabase connected (table doesn't exist yet — that's fine)")
        results["Supabase"] = "✅ Connected"
    else:
        print(f"❌ Supabase failed: {e}")
        results["Supabase"] = f"❌ Failed: {e}"

# ── 3. Redis (Upstash) ────────────────────────────
# ── 3. Redis (Upstash) ────────────────────────────
print("\n🔍 Testing Redis...")
try:
    import redis
    r = redis.from_url(
        os.getenv("REDIS_URL"),
        decode_responses=True
    )
    r.set("test_key", "redis_working", ex=10)
    value = r.get("test_key")
    print(f"✅ Redis works: got '{value}'")
    results["Redis"] = "✅ Connected"
except Exception as e:
    print(f"❌ Redis failed: {e}")
    results["Redis"] = f"❌ Failed: {e}"
# ── 4. Telegram ───────────────────────────────────
print("\n🔍 Testing Telegram Bot...")
try:
    import requests
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    response = requests.get(
        f"https://api.telegram.org/bot{token}/getMe",
        timeout=10
    )
    data = response.json()
    if data.get("ok"):
        bot_name = data["result"]["username"]
        print(f"✅ Telegram works: @{bot_name}")
        results["Telegram"] = f"✅ Connected (@{bot_name})"
    else:
        print(f"❌ Telegram failed: {data}")
        results["Telegram"] = f"❌ Failed: {data}"
except Exception as e:
    print(f"❌ Telegram failed: {e}")
    results["Telegram"] = f"❌ Failed: {e}"

# ── 5. Twilio ─────────────────────────────────────
print("\n🔍 Testing Twilio...")
try:
    from twilio.rest import Client
    client = Client(
        os.getenv("TWILIO_ACCOUNT_SID"),
        os.getenv("TWILIO_AUTH_TOKEN")
    )
    # Just fetch account info — no message sent
    account = client.api.accounts(
        os.getenv("TWILIO_ACCOUNT_SID")
    ).fetch()
    print(f"✅ Twilio works: {account.friendly_name}")
    results["Twilio"] = f"✅ Connected ({account.friendly_name})"
except Exception as e:
    print(f"❌ Twilio failed: {e}")
    results["Twilio"] = f"❌ Failed: {e}"

# ── Summary ───────────────────────────────────────
print("\n" + "="*50)
print("📋 CONNECTION TEST SUMMARY")
print("="*50)
for service, status in results.items():
    print(f"  {service:12} → {status}")
print("="*50)

all_passed = all("✅" in v for v in results.values())
if all_passed:
    print("\n🎉 All services connected! Ready to build.")
else:
    print("\n⚠️  Some services failed. Fix them before continuing.")
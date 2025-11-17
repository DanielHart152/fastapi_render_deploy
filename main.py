from fastapi import FastAPI, Request
import requests, json, os, hashlib, hmac, re, time
from dotenv import load_dotenv
from openai import OpenAI
from datetime import datetime, timedelta
import httpx


app = FastAPI()

@app.get("/")
async def root():
    return {"message": "Chafinity WhatsApp Bot is running!"}

load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Initialize OpenAI client only when needed
client = None

VERIFY_TOKEN = "mysecuretoken1475"
ACCESS_TOKEN = "EAAbbSke4OukBPZB5dM6sMuufW4ZAFgnoZALMlOsf69ZA84my5yVrZC3z6p2UDYQmijVr8kD3VkfjTNycYlKqgItdfyXxriE1Ypr4i5cIEhepHGPXqZB8olHAMZAA1pWy2DueFq0Y2Us7vzyOCLZB4eIUa1lhRfEXxtAWnFPhCL3uhfxppNO2sJs1OjDGIZCU0MLSZAxFZA4Te3LZCq9pcKAZANP8NpZBD860TuV75lHDdh"
PHONE_NUMBER_ID = "885195624673209"

PAYSTACK_SECRET = os.getenv("PAYSTACK_SECRET_KEY")
PAYSTACK_BASE = os.getenv("PAYSTACK_BASE")

processed_messages = set()
user_sessions = {}
payments = {}

# ---------- VERIFY WEBHOOK ----------
@app.get("/webhook")
async def verify_webhook(request: Request):
    mode = request.query_params.get("hub.mode")
    token = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge")
    if mode == "subscribe" and token == VERIFY_TOKEN:
        print("Webhook verified successfully.")
        return int(challenge)
    print("Webhook verification failed.")
    return {"error": "Verification failed"}

@app.post("/webhook")
async def receive_message(request: Request):
    data = await request.json()
    print("Incoming data:", json.dumps(data, indent=2))

    try:
        for entry in data.get("entry", []):
            for change in entry.get("changes", []):
                value = change.get("value", {})

                # Ignore delivery updates and read receipts
                if "statuses" in value:
                    continue

                messages = value.get("messages", [])
                if not messages:
                    continue

                msg = messages[0]
                msg_id = msg.get("id")
                sender = msg.get("from")
                msg_type = msg.get("type")

                # Only process text messages
                if msg_type != "text":
                    continue

                text = msg.get("text", {}).get("body", "").strip()

                # Avoid duplicate processing
                if msg_id in processed_messages:
                    print(f"Duplicate ignored: {msg_id}")
                    continue
                processed_messages.add(msg_id)

                # Maintain user conversation history
                if sender not in user_sessions:
                    user_sessions[sender] = {"conversation": [], "greeting_sent": False}

                session = user_sessions[sender]

                # --- Handle greeting message (sent only once) ---
                if not session["greeting_sent"] and len(session["conversation"]) == 0:
                    
                    send_reply(sender, "Hello! 👋 How far? 😊 How I fit help you today? Need any WiFi plans or anything? 📶🔥")
                    
                    session["greeting_sent"] = True
                    # DO NOT append a fake assistant message that confuses context
                    continue

                # --- Detect email + price in same message ---
                email_pattern = r"[^@]+@[^@]+\.[^@]+"
                price_pattern = r"\b(250|450|1000|1500|8000|4000|20000|25000)\b"

                email_found = re.search(email_pattern, text)
                price_found = re.search(price_pattern, text)

                # CASE 1: User sends BOTH email + price in same message (valid)
                email_pattern = r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"
                price_pattern = r"\b(250|450|1000|1500|8000|4000|20000|25000)\b"

                email_found = re.search(email_pattern, text)
                price_found = re.search(price_pattern, text)

                if email_found and price_found:
                    email = email_found.group(0).strip()
                    amount = int(price_found.group(0))
                    send_reply(sender, f"Perfect! Email {email} and price ₦{amount} confirmed. Generating your secure payment link... 💬")
                    send_reply(sender,
                        "Boss, quick one...\nMark Angel & Emmanuella blow because dem start early online.\n"
                        "People mock them that year — but early movers always win.\n\n"
                        "Right now, AI dey give you that same early-mover advantage.\n"
                        "But no worry, if na WiFi you want first, I dey here for you.\n\n"
                    )

                    try:
                        headers = {
                            "Authorization": f"Bearer {os.getenv('PAYSTACK_SECRET_KEY')}",
                            "Content-Type": "application/json"
                        }
                        payload = {"email": email, "amount": int(amount) * 100}
                        response = requests.post("https://api.paystack.co/transaction/initialize", headers=headers, json=payload, timeout=15)
                        data = response.json()
                        if data.get("status"):
                            ref = data["data"]["reference"]
                            payments[ref] = {"sender": sender, "plan": amount, "email": email}
                            link = data["data"]["authorization_url"]
                            send_reply(sender, f"✅ Here is your secure payment link:\n{link}\n\nPlease complete payment to activate your plan.")
                        else:
                            send_reply(sender, "⚠️ Could not generate payment link. Please try again.")
                    except Exception as e:
                        print("Payment initiation error:", e)
                        send_reply(sender, "⚠️ Something went wrong while creating your payment link.")
                    
                    continue

                # CASE 2: User sends ONLY email
                if email_found and not price_found:
                    send_reply(
                        sender,
                        "Nice one! But abeg send both email and price together like this: 'email@gmail.com 4000' 🔴"
                    )
                    continue

                # CASE 3: User sends ONLY price
                if price_found and not email_found:
                    send_reply(
                        sender,
                        "I see the price 👌 but I still need your email. Drop both together like this: 'email@gmail.com 4000' 🔴"
                    )
                    continue

                # CASE 4: User sends something else while confirming
                if "@" in text or any(p in text for p in ["250","450","1000","1500","8000","4000","20000","25000"]):
                    send_reply(
                        sender,
                        "Abeg send am properly. Use this format: 'email@gmail.com 4000' so I fit confirm everything 🙏"
                    )
                    continue

                # --- Otherwise, use AI to generate natural conversation responses ---
                # append user message first so the model sees full context
                session["conversation"].append({"role": "user", "content": text})

                # strengthen instruction: do not greet if greeting already sent
                if session.get("greeting_sent"):
                    # add a short system-level guard into the message list to discourage extra greetings
                    session_context = session["conversation"] + [{"role":"system","content":"Do not send greetings like 'hello', 'hi', or 'hello again'. Reply directly to the user's request."}]
                else:
                    session_context = session["conversation"]

                reply = get_ai_reply(session_context, text)
                # small post-filter: if greeting already sent and model still greets, replace with neutral reply
                if session.get("greeting_sent") and re.search(r"\b(hi|hello|hey|how far|how you)\b", reply, re.I):
                    reply = "I got you — how can I help you with the plan or payment? Please drop your email if you want the link."
                send_reply(sender, reply)

                # append assistant message after sending
                session["conversation"].append({"role": "assistant", "content": reply})

                user_sessions[sender] = session

    except Exception as e:
        print("Error:", e)

    return {"status": "ok"}

# ---------- OPENAI CHAT ----------

def get_ai_reply(conversation, user_message):
    global client

    # Extra: remove Render's proxy variables (still useful)
    for var in ["HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"]:
        os.environ.pop(var, None)

    if client is None:
        try:
            import httpx
            http_client = httpx.Client(trust_env=False)  # <- CRUCIAL FIX
            client = OpenAI(
                api_key=OPENAI_API_KEY,
                http_client=http_client,
                timeout=30.0
            )
        except TypeError as e:
            print(f"OpenAI client initialization error: {e}")
            client = OpenAI(api_key=OPENAI_API_KEY)

    system_prompt = (
        "You are Chafinity 📶, a warm Nigerian WiFi assistant that also promotes ChaFinity AI automation. "
        "After any WiFi interaction, naturally mention that the same AI brain can help the user automate their business — "
        "find customers, negotiate, and close sales 24/7."
        "You sound human — not robotic. You only greet naturally once, "
        "then continue conversations casually and kindly. "
        "Use Nigerian English and light Pidgin sometimes, with a touch of humor. "
        "You handle questions about WiFi plans, prices, and purchases naturally. "
        "If a user mentions another city or country such as Kyiv or London, politely inform them that service is not yet available there. "
        "When the user chooses a plan and wants to buy, ALWAYS ask them to confirm with BOTH their email and the plan price in one message, like: email@gmail.com 1000. "
        "When the user sends both email + price correctly, confirm and say you’re generating the payment link. "
        "When users say thanks or small talk, reply naturally. "
        "Use friendly emojis like 🔴, 📶, 💬, and ✅ when suitable. "
        "Available plans:\n"
        "1️⃣ ₦250 (12h)\n2️⃣ ₦450 (24h)\n3️⃣ ₦1000 (3 days)\n4️⃣ ₦1500 (1 week)\n"
        "5️⃣ ₦8000 (1 week heavy)\n6️⃣ ₦4000 (1 month)\n7️⃣ ₦1000 (1 month POS)\n"
        "8️⃣ ₦20000 (market device)\n9️⃣ ₦25000 (home unlimited)\n"
        "Be conversational, funny sometimes, and never repeat same intro."
    )

    conversation = conversation[-10:]

    messages = [{"role": "system", "content": system_prompt}] + conversation

    try:
        completion = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            temperature=0.8
        )
        return completion.choices[0].message.content.strip()
    except Exception as e:
        print("AI Error:", e)
        return "Wahala small 😅. Try message me again shortly."


# ---------- PAYSTACK ----------

def initiate_payment(sender, email, amount):
    try:
        headers = {"Authorization": f"Bearer {PAYSTACK_SECRET}", "Content-Type": "application/json"}
        payload = {"email": email, "amount": int(amount) * 100}
        res = requests.post(f"{PAYSTACK_BASE}/transaction/initialize", headers=headers, json=payload, timeout=15)
        data = res.json()

        if data.get("status"):
            ref = data["data"]["reference"]
            link = data["data"]["authorization_url"]
            payments[ref] = {"sender": sender, "email": email, "plan": amount}
            send_reply(sender, f"✅ Here's your secure payment link:\n{link}\n\nOnce you complete payment, your WiFi code will be sent automatically 📶")
        else:
            send_reply(sender, "⚠️ Could not generate payment link. Please try again.")
    except Exception as e:
        print("Payment init error:", e)
        send_reply(sender, "⚠️ Something went wrong while generating payment link.")

# ---------- PAYSTACK WEBHOOK ----------
@app.post("/pay/webhook")
async def paystack_webhook(request: Request):
    payload = await request.body()
    sig = request.headers.get("x-paystack-signature")
    computed_sig = hmac.new(PAYSTACK_SECRET.encode(), msg=payload, digestmod=hashlib.sha512).hexdigest()
    if sig != computed_sig:
        return {"error": "Invalid signature"}

    data = json.loads(payload)
    print("Paystack Webhook:", json.dumps(data, indent=2))

    if data.get("event") == "charge.success":
        ref = data["data"]["reference"]
        amount = data["data"]["amount"] / 100
        info = payments.pop(ref, None)
        if not info:
            return {"status": "ok"}

        sender = info["sender"]
        send_reply(sender, f"✅ Payment of ₦{amount} confirmed. Generating your WiFi code... please wait 💬")
        try:
            headers = {
                "cloud-key": os.getenv("CLOUD_KEY"),
                "gateway-id": os.getenv("GATEWAY_ID"),
                "group-id": os.getenv("GROUP_ID"),
                "Content-Type": "application/json"
            }
            minutes = 30 * 24 * 60
            now = datetime.utcnow()
            payload = {
                "addcode": {
                    "start": now.strftime("%Y-%m-%d %H:%M:%S"),
                    "end": (now + timedelta(minutes=minutes)).strftime("%Y-%m-%d %H:%M:%S")
                }
            }
            resp = requests.post("https://demo.guest-internet.com/api/", headers=headers, json=payload, timeout=20)
            wifi_resp = resp.json()
            code = wifi_resp.get("addcode", {}).get("code") or (wifi_resp.get("codes", [{}])[0].get("code") if "codes" in wifi_resp else None)
            if code:
                send_reply(sender, f"🎉 Done! Your WiFi code is {code}. Enjoy fast browsing with Chafinity 📶")
                send_reply(
                    sender,
                    "Boss, now your WiFi don active — but make I show you something powerful.\n\n"
                    "This same AI brain wey just handle your purchase fit run your business on autopilot:\n"
                    "- show customers your products\n"
                    "- negotiate like human\n"
                    "- close sales 24/7\n\n"
                    "Early movers always win. Mark Angel no wait.\n"
                    "Visit ChaFinity.ng and let your AI start selling while you sleep. ⚡️"
                )
            else:
                send_reply(sender, "✅ Payment confirmed but code unavailable. Contact support please.")
        except Exception as e:
            print("WiFi code error:", e)
            send_reply(sender, "✅ Payment confirmed but WiFi code generation failed. Contact support.")
    return {"status": "ok"}

# ---------- WHATSAPP SEND ----------
def send_reply(to, message):
    url = f"https://graph.facebook.com/v20.0/{PHONE_NUMBER_ID}/messages"
    headers = {"Authorization": f"Bearer {ACCESS_TOKEN}", "Content-Type": "application/json"}
    payload = {"messaging_product": "whatsapp", "to": to, "type": "text", "text": {"body": message}}
    try:
        res = requests.post(url, headers=headers, json=payload)
        print("Reply sent:", res.status_code, res.text)
    except Exception as e:
        print("Send error:", e)
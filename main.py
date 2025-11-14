from fastapi import FastAPI, Request
import requests, json, os, hashlib, hmac, re, time
from dotenv import load_dotenv
from openai import OpenAI
from datetime import datetime, timedelta

app = FastAPI()

@app.get("/")
async def root():
    return {"message": "Chafinity WhatsApp Bot is running!"}

load_dotenv()
print("PAYSTACK_SECRET_KEY:", os.getenv("PAYSTACK_SECRET_KEY"))
print("PAYSTACK_BASE:", os.getenv("PAYSTACK_BASE"))
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Initialize OpenAI client only when needed
client = None

VERIFY_TOKEN = "mysecuretoken1475"
ACCESS_TOKEN = "EAAbbSke4OukBP2kqAHRsjQ2J6Hy3ZAbJIzaJzhharZARGrVQV1SmVmEQGJM4NwdMuxNm84n17glmXiNxxCOZCl3D4J4G6HqlWznud3kPQbMKpKHeLkoVCkgWj7xKTTg06Gmk3h1yinJCyPjhh537AaEDZC1PPFJnMc74F5xzi7gBTIXZB6MpXu5pcFdK26gmZAOYHBZAejQD1wFs2DiYc5yLodou2ZBdQZCNvFCCjwInU5ZBxg3ZBXaeZCl30EgIeAZDZD"
PHONE_NUMBER_ID = "885195624673209"

PAYSTACK_SECRET = os.getenv("PAYSTACK_SECRET_KEY")
PAYSTACK_BASE = os.getenv("PAYSTACK_BASE")

processed_messages = set()
user_sessions = {}  # Track conversation states per user
payments = {}


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
                messages = value.get("messages", [])

                if not messages:
                    continue

                msg = messages[0]
                msg_id = msg["id"]
                sender = msg["from"]
                text = msg.get("text", {}).get("body", "").strip()

                if msg_id in processed_messages:
                    print(f"Duplicate message {msg_id}, skipping.")
                    continue
                processed_messages.add(msg_id)

                print(f"Received new message {msg_id} from {sender}: {text}")

                # Initialize session
                if sender not in user_sessions:
                    user_sessions[sender] = {"stage": "start"}

                stage = user_sessions[sender]["stage"]

                # --- Chat flow ---
                if stage == "start":
                    send_reply(sender, "Welcome to Chafinity 📶! Please reply with the number of your desired plan:\n\n1️⃣ ₦250 (12h)\n2️⃣ ₦450 (24h)\n3️⃣ ₦1000 (3 days)\n4️⃣ ₦1500 (1 week)\n5️⃣ ₦8000 (1 week heavy)\n6️⃣ ₦4000 (1 month)\n7️⃣ ₦1000 (1 month POS)\n8️⃣ ₦20000 (market device)\n9️⃣ ₦25000 (home unlimited)\n\nReply with a number to continue.")
                    user_sessions[sender]["stage"] = "awaiting_plan"
                    continue

                elif stage == "awaiting_plan":
                    amount_map = {"1": 250, "2": 450, "3": 1000, "4": 1500, "5": 8000, "6": 4000, "7": 1000, "8": 20000, "9": 25000}
                    amount = amount_map.get(text)

                    if amount:
                        user_sessions[sender]["amount"] = amount
                        user_sessions[sender]["stage"] = "awaiting_email"
                        send_reply(sender, f"✅ Great! You selected ₦{amount}. Please type your email address to receive your payment link.")
                    else:
                        send_reply(sender, "⚠️ Please reply with a valid plan number (1–9).")
                    continue

                elif stage == "awaiting_email":
                    email = text
                    user_sessions[sender]["email"] = email
                    amount = user_sessions[sender]["amount"]

                    send_reply(sender, "Generating your payment link... please wait 💬")

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
                            # link = data["data"]["authorization_url"]
                            # send_reply(sender, f"✅ Here is your secure payment link:\n{link}\n\nPlease complete your payment to activate your plan.")
                        else:
                            send_reply(sender, "⚠️ Could not generate payment link. Please try again.")
                    except Exception as e:
                        print("Payment initiation error:", e)
                        send_reply(sender, "⚠️ Something went wrong while creating your payment link.")

                    # Reset session after sending payment link
                    user_sessions[sender] = {"stage": "start"}
                    continue

                    # try:
                    #     pay_response = requests.post(
                    #         "https://fastapi-render-deploy-qv0j.onrender.com/pay/initiate",
                    #         json={"email": email, "amount": amount},
                    #         timeout=20
                    #     )
                    #     result = pay_response.json()
                    #     if result.get("status") == "success":
                    #         link = result["authorization_url"]
                    #         send_reply(sender, f"✅ Here is your secure payment link:\n{link}\n\nPlease complete your payment to activate your plan.")
                    #     else:
                    #         send_reply(sender, "⚠️ Sorry, I couldn’t create your payment link. Please try again.")
                    # except Exception as e:
                    #     print("Payment initiation error:", e)
                    #     send_reply(sender, "⚠️ Something went wrong while creating your payment link.")

                    # # Reset session after sending payment link
                    # user_sessions[sender] = {"stage": "start"}
                    # continue
                    
                # --- Fallback to AI for other messages ---
                ai_reply = get_ai_reply(text)
                send_reply(sender, ai_reply)

    except Exception as e:
        print("Error while handling message:", e)

    return {"status": "ok"}


@app.post("/pay/initiate")
async def initiate_payment(request: Request):
    body = await request.json()
    email = body.get("email")
    amount = body.get("amount")

    if not email or not amount:
        return {"error": "Email and amount are required"}

    try:
        headers = {
            "Authorization": f"Bearer {os.getenv('PAYSTACK_SECRET_KEY')}",
            "Content-Type": "application/json"
        }
        payload = {"email": email, "amount": int(amount) * 100}

        response = requests.post(f"{os.getenv('PAYSTACK_BASE')}/transaction/initialize", headers=headers, json=payload, timeout=15)
        data = response.json()
        print("Response text:", response.text)
        print("Paystack Init Response:", data)

        if data.get("status"):
            checkout_url = data["data"]["authorization_url"]
            reference = data["data"]["reference"]
            return {"status": "success", "authorization_url": checkout_url, "reference": reference}
        else:
            return {"status": "failed", "message": data.get("message", "Initialization failed")}

    except Exception as e:
        print("Error initializing payment:", e)
        return {"error": "Payment initialization failed"}


@app.post("/pay/webhook")
async def paystack_webhook(request: Request):
    payload = await request.body()
    sig = request.headers.get("x-paystack-signature")

    secret = os.getenv("PAYSTACK_SECRET_KEY")
    computed_sig = hmac.new(secret.encode(), msg=payload, digestmod=hashlib.sha512).hexdigest()
    if sig != computed_sig:
        print("Invalid signature received")
        return {"error": "Invalid signature"}

    data = json.loads(payload)
    print("Webhook received:", json.dumps(data, indent=2))

    if data.get("event") == "charge.success":
        ref = data["data"]["reference"]
        amount = data["data"]["amount"] / 100
        customer_email = data["data"]["customer"]["email"]
        info = payments.get(ref) or next((v for v in payments.values() if v.get("email") == customer_email), None)

        if info:
            sender = info["sender"]
            plan = info["plan"]

            # --- Generate WiFi access code from Guest Internet API ---
            try:
                headers = {
                    "cloud-key": os.getenv("CLOUD_KEY"),
                    "gateway-id": os.getenv("GATEWAY_ID"),
                    "group-id": os.getenv("GROUP_ID"),
                    "Content-Type": "application/json"
                }

                # map plan amount to duration in minutes
                plan_minutes = {
                    250: 12*60, 450: 24*60, 1000: 3*24*60, 1500: 7*24*60,
                    8000: 7*24*60, 4000: 30*24*60, 1000: 30*24*60,
                    20000: 30*24*60, 25000: 30*24*60
                }

                minutes = plan_minutes.get(plan, 24*60)
                now = datetime.utcnow()
                start = now.strftime("%Y-%m-%d %H:%M:%S")
                end = (now + timedelta(minutes=minutes)).strftime("%Y-%m-%d %H:%M:%S")
                payload = {"addcode": {"start": start, "end": end}}

                print("Guest Internet payload:", payload)
                print("Guest Internet headers:", {k: v for k, v in headers.items() if v})
                resp = requests.post("https://demo.guest-internet.com/api/", headers=headers, json=payload, timeout=20)
                print("Guest Internet status:", resp.status_code)
                print("Guest Internet raw response:", resp.text)

                wifi_response = None
                try:
                    wifi_response = resp.json()
                except Exception as e:
                    print("JSON decode error:", e)

                code = None
                if isinstance(wifi_response, dict):
                    if "addcode" in wifi_response and isinstance(wifi_response["addcode"], dict):
                        code = wifi_response["addcode"].get("code")
                    elif "codes" in wifi_response and isinstance(wifi_response["codes"], list) and wifi_response["codes"]:
                        code = wifi_response["codes"][0].get("code")

                if code:
                    send_reply(sender, f"✅ Payment of ₦{amount} confirmed. Your WiFi code is {code}. Enjoy your connection 📶")
                else:
                    print("No WiFi code found in response:", wifi_response)
                    send_reply(sender, "✅ Payment confirmed, but failed to generate WiFi code. Please contact support.")

            except Exception as e:
                print("WiFi code generation exception:", e)
                send_reply(sender, "✅ Payment confirmed, but there was an issue generating your access code.")

            payments.pop(ref, None)
        else:
            print("Payment confirmed but no mapping found for reference:", ref)

    return {"status": "ok"}

def get_ai_reply(user_message):
    try:
        global client
        if client is None:
            client = OpenAI(api_key=OPENAI_API_KEY)
            
        data_plans = """
        🔴 *Available Internet Plans* (All Prices in ₦aira):
        • 1️⃣ One-day, 12-hour unlimited – ₦250
        • 2️⃣ One-day, 24-hour unlimited – ₦450
        • 3️⃣ 3-day unlimited – ₦1,000
        • 4️⃣ 1-week unlimited – ₦1,500
        • 5️⃣ 1-week heavy browsing – ₦8,000
        • 6️⃣ 1-month unlimited – ₦4,000
        • 7️⃣ 1-month POS unlimited – ₦1,000
        • 8️⃣ 1-month market device – ₦20,000
        • 9️⃣ Home unlimited (1 month, 8 devices) – ₦25,000
        """

        system_prompt = (
            "You are *Chafinity*, a friendly AI assistant for a Nigerian internet provider. "
            "Your job is to guide users on available data plans, coverage, and service help. "
            "If they ask about locations outside Ariaria International Market (Aba, Nigeria), politely say service is not yet available there. "
            "Keep tone warm and natural with Nigerian English flavor, and use emojis like 🔴📶✅💬 naturally.\n\n"
            f"{data_plans}"
        )

        completion = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_message}]
        )
        ai_text = completion.choices[0].message.content.strip()
        print("AI Reply:", ai_text)
        return ai_text
    except Exception as e:
        print("Error from OpenAI:", e)
        return "Sorry, I'm having a bit of trouble processing your request right now."


def send_reply(to, message):
    url = f"https://graph.facebook.com/v20.0/{PHONE_NUMBER_ID}/messages"
    headers = {"Authorization": f"Bearer {ACCESS_TOKEN}", "Content-Type": "application/json"}
    payload = {"messaging_product": "whatsapp", "to": to, "type": "text", "text": {"body": message}}

    print(f"Sending reply to {to}...")
    response = requests.post(url, headers=headers, json=payload)
    print("Status Code:", response.status_code)
    print("Response:", response.text)

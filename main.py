from fastapi import FastAPI, Request
import requests, json, os, hashlib, hmac
from dotenv import load_dotenv
from openai import OpenAI

app = FastAPI()

load_dotenv()
print("PAYSTACK_SECRET_KEY:", os.getenv("PAYSTACK_SECRET_KEY"))
print("PAYSTACK_BASE:", os.getenv("PAYSTACK_BASE"))
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Initialize OpenAI client only when needed
client = None

VERIFY_TOKEN = "mysecuretoken1475"
ACCESS_TOKEN = "EAAbbSke4OukBP6adhLvkNxolN5UgeoMZAhJDdtiniqThcqN6qyZAEZBkcia2DKxzHpSopQxLb5qTAvNpYREyjK1FAYZA3IyH58VSASbscsMtKmK56aYEArSqta4Y3UXSZBJtI73urqHKNWN2lOVb7qHpTDh1NFZCID6ReHUZA2mCqAPk8NsYLLIovLuT2uPcoqNIFE3blZBgQVHkZCx2jXOPXLevqL6aMN38SUVrukj4ISpZBhuEwpNy2vLy7iEnG8KSe3dyVMZCPROQTs1nHjK0gfP9YKOLPqG88iSQgZDZD"
PHONE_NUMBER_ID = "239491695904026"

processed_messages = set()
user_sessions = {}  # Track conversation states per user


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
                        pay_response = requests.post(
                            "http://54.200.235.123:8000/pay/initiate",
                            json={"email": email, "amount": amount},
                            timeout=20
                        )
                        result = pay_response.json()
                        if result.get("status") == "success":
                            link = result["authorization_url"]
                            send_reply(sender, f"✅ Here is your secure payment link:\n{link}\n\nPlease complete your payment to activate your plan.")
                        else:
                            send_reply(sender, "⚠️ Sorry, I couldn’t create your payment link. Please try again.")
                    except Exception as e:
                        print("Payment initiation error:", e)
                        send_reply(sender, "⚠️ Something went wrong while creating your payment link.")

                    # Reset session after sending payment link
                    user_sessions[sender] = {"stage": "start"}
                    continue

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
        return {"error": "Invalid signature"}

    data = json.loads(payload)
    print("Webhook received:", json.dumps(data, indent=2))

    if data.get("event") == "charge.success":
        email = data["data"]["customer"]["email"]
        amount = data["data"]["amount"] / 100
        print(f"✅ Payment successful from {email} for ₦{amount}")
        # You can now trigger plan activation or WiFi code delivery here.

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

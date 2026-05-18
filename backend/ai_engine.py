"""
ai_engine.py — Groq LLM personalised email generation
Smart-Shop AI Engine
"""

import os
from groq import Groq
from dotenv import load_dotenv

load_dotenv()

client      = Groq(api_key=os.getenv("GROQ_API_KEY"))
SENDER_NAME = os.getenv("SENDER_NAME", "Smart-Shop")
MODEL       = "llama-3.3-70b-versatile"  # fast, free Groq model


# ── Email Generator ───────────────────────────────────────────────────────────

def generate_email(
    customer_name:    str,
    cart_items:       list[dict],
    total_cart_value: float,
    churn_probability: float,
    discount_code:    str = "SAVE10",
) -> dict:
    """
    Generate a personalised win-back email using Groq LLM.

    Returns
    -------
    dict:
        subject : str
        body    : str
    """

    # Build a readable cart summary
    if cart_items:
        cart_lines = "\n".join(
            f"  • {item['title']} (x{item['quantity']}) — ${item['price']:.2f}"
            for item in cart_items
        )
    else:
        cart_lines = "  • Items in your cart"

    risk_label = (
        "very likely to leave without purchasing"  if churn_probability >= 0.65 else
        "at moderate risk of abandoning their cart" if churn_probability >= 0.40 else
        "showing early signs of cart abandonment"
    )

    prompt = f"""You are a friendly, warm customer service agent for {SENDER_NAME}, a beauty e-commerce brand.

A customer named "{customer_name}" has left the following items in their cart:
{cart_lines}

Cart Total: ${total_cart_value:.2f}
Our AI model indicates this customer is {risk_label} (churn probability: {churn_probability:.0%}).

Write a SHORT, personalised win-back email with:
1. A compelling subject line (start with "Subject: ")
2. A warm greeting using their first name
3. A friendly 2-3 sentence reminder about their cart
4. Offer them a 10% discount code: {discount_code}
5. A clear call-to-action to complete their purchase
6. A warm sign-off from {SENDER_NAME}

Rules:
- Tone: warm, genuine, never pushy or spammy
- Total email body: 5-7 sentences max
- Mention at least one specific product from their cart
- Do NOT mention "AI", "churn", "probability", or any technical terms
- Format: Subject line first, then blank line, then email body

Write the email now:"""

    response = client.chat.completions.create(
        model    = MODEL,
        messages = [{"role": "user", "content": prompt}],
        max_tokens  = 400,
        temperature = 0.75,
    )

    raw_text = response.choices[0].message.content.strip()
    return _parse_email(raw_text, customer_name, cart_items, discount_code)


def _parse_email(raw: str, customer_name: str,
                 cart_items: list, discount_code: str) -> dict:
    """Split LLM output into subject + body."""
    lines   = raw.strip().splitlines()
    subject = ""
    body_lines = []

    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.lower().startswith("subject:"):
            subject = stripped[8:].strip()
        else:
            body_lines.append(stripped)

    body = "\n".join(body_lines).strip()

    # Fallback subject if LLM didn't include one
    if not subject:
        first_item = cart_items[0]["title"] if cart_items else "your cart"
        subject = f"You left {first_item} behind 💛 — Here's 10% off to complete your order"

    # Fallback body
    if not body:
        first_name = customer_name.split()[0] if customer_name else "there"
        first_item = cart_items[0]["title"] if cart_items else "your items"
        body = (
            f"Hi {first_name},\n\n"
            f"We noticed you left {first_item} in your cart. "
            f"We'd love to help you complete your purchase!\n\n"
            f"Use code {discount_code} for 10% off your order today.\n\n"
            f"Warm regards,\n{os.getenv('SENDER_NAME', 'Smart-Shop')}"
        )

    return {"subject": subject, "body": body}


# ── Smoke test ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    sample_items = [
        {"title": "Rose Glow Serum",   "quantity": 1, "price": 34.99},
        {"title": "Vitamin C Moisturiser", "quantity": 1, "price": 24.99},
    ]
    result = generate_email(
        customer_name     = "Sarah Ahmed",
        cart_items        = sample_items,
        total_cart_value  = 59.98,
        churn_probability = 0.82,
        discount_code     = "SAVE10",
    )
    print("=" * 60)
    print("SUBJECT:", result["subject"])
    print("-" * 60)
    print(result["body"])
    print("=" * 60)

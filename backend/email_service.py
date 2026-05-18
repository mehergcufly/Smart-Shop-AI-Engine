"""
email_service.py — Gmail SMTP email sender (Anti-spam + Professional HTML)
Smart-Shop AI Engine
"""

import os
import smtplib
import uuid
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.utils import formatdate, make_msgid
from datetime import datetime
from dotenv import load_dotenv
from sqlalchemy.orm import Session
from database import EmailHistory

load_dotenv()

GMAIL_ADDRESS  = os.getenv("GMAIL_ADDRESS")
GMAIL_APP_PASS = os.getenv("GMAIL_APP_PASSWORD")
SENDER_NAME    = os.getenv("SENDER_NAME", "Sia Glow Beauty")
SHOP_URL       = os.getenv("SHOPIFY_SHOP", "sia-glow")
SHOP_DOMAIN    = f"https://{SHOP_URL}.myshopify.com"


# ── Core Send ─────────────────────────────────────────────────────────────────

def send_email(
    to_email: str,
    subject: str,
    body: str,
    cart_url: str = "",
    cart_items: list = None,
    total_cart_value: float = 0.0,
    discount_code: str = "SAVE10",
    customer_name: str = "Valued Customer",
) -> dict:
    """
    Send a professional HTML email via Gmail SMTP with anti-spam headers.
    """
    if not to_email or "@" not in to_email:
        return {"success": False, "error": f"Invalid or missing email: '{to_email}'"}
    if not GMAIL_ADDRESS or not GMAIL_APP_PASS:
        return {"success": False, "error": "Gmail credentials not configured in .env"}

    try:
        msg = MIMEMultipart("alternative")

        # ── Anti-spam headers ──────────────────────────────────────────────
        msg["Subject"]      = subject
        msg["From"]         = f"{SENDER_NAME} <{GMAIL_ADDRESS}>"
        msg["To"]           = to_email
        msg["Date"]         = formatdate(localtime=True)
        msg["Message-ID"]   = make_msgid(domain=GMAIL_ADDRESS.split("@")[1])
        msg["Reply-To"]     = GMAIL_ADDRESS
        msg["List-Unsubscribe"] = f"<mailto:{GMAIL_ADDRESS}?subject=unsubscribe>"
        msg["List-Unsubscribe-Post"] = "List-Unsubscribe=One-Click"
        msg["Feedback-ID"]  = f"cart-recovery:{GMAIL_ADDRESS.split('@')[0]}:sia-glow"
        msg["X-Entity-Ref-ID"] = str(uuid.uuid4())
        msg["Precedence"]   = "bulk"
        msg["X-Mailer"]     = "SiaGlowBeauty-CartRecovery/1.0"

        first_name = customer_name.split()[0] if customer_name else "there"
        cart_link  = cart_url or SHOP_DOMAIN

        # Plain text (required for anti-spam scoring)
        plain = _make_plain(body, discount_code, cart_link)
        html  = _make_html(
            body=body,
            subject=subject,
            first_name=first_name,
            discount_code=discount_code,
            cart_link=cart_link,
            cart_items=cart_items or [],
            total_cart_value=total_cart_value,
        )

        msg.attach(MIMEText(plain, "plain", "utf-8"))
        msg.attach(MIMEText(html,  "html",  "utf-8"))

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.ehlo()
            server.login(GMAIL_ADDRESS, GMAIL_APP_PASS)
            server.sendmail(GMAIL_ADDRESS, to_email, msg.as_string())

        print(f"✅ Email sent → {to_email}")
        return {"success": True, "error": None}

    except smtplib.SMTPAuthenticationError:
        err = "Gmail auth failed — check GMAIL_APP_PASSWORD in .env"
        print(f"❌ {err}")
        return {"success": False, "error": err}
    except Exception as e:
        print(f"❌ Email error: {e}")
        return {"success": False, "error": str(e)}


# ── Pipeline: generate + send + log ──────────────────────────────────────────

def send_and_log(
    db: Session,
    customer_id: str,
    customer_email: str,
    customer_name: str,
    subject: str,
    body: str,
    churn_probability: float,
    discount_code: str = "SAVE10",
    sent_manually: bool = False,
    cart_items: list = None,
    total_cart_value: float = 0.0,
    cart_url: str = "",
) -> dict:
    result = send_email(
        to_email=customer_email,
        subject=subject,
        body=body,
        cart_url=cart_url,
        cart_items=cart_items or [],
        total_cart_value=total_cart_value,
        discount_code=discount_code,
        customer_name=customer_name,
    )

    record = EmailHistory(
        customer_id       = customer_id,
        customer_email    = customer_email,
        customer_name     = customer_name,
        churn_probability = churn_probability,
        email_subject     = subject,
        email_body        = body,
        discount_code     = discount_code,
        sent_manually     = sent_manually,
        send_status       = "sent" if result["success"] else "failed",
        error_message     = result.get("error"),
        sent_at           = datetime.utcnow() if result["success"] else None,
    )
    db.add(record)
    db.commit()
    db.refresh(record)

    return {
        "success":    result["success"],
        "error":      result.get("error"),
        "history_id": record.id,
    }


# ── Plain text builder ────────────────────────────────────────────────────────

def _make_plain(body: str, discount_code: str, cart_link: str) -> str:
    return (
        f"{body}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"Your exclusive discount code: {discount_code}\n"
        f"Complete your purchase here: {cart_link}\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"To unsubscribe, reply with 'unsubscribe' in the subject.\n"
        f"© {datetime.utcnow().year} {SENDER_NAME}"
    )


# ── Professional HTML template ────────────────────────────────────────────────

def _make_html(
    body: str,
    subject: str,
    first_name: str,
    discount_code: str,
    cart_link: str,
    cart_items: list,
    total_cart_value: float,
) -> str:

    # Build cart items rows
    items_html = ""
    if cart_items:
        rows = ""
        for item in cart_items:
            title = item.get("title", "Item")
            qty   = item.get("quantity", 1)
            price = item.get("price", 0)
            rows += f"""
            <tr>
              <td style="padding:10px 0;border-bottom:1px solid #f0e8df;
                         font-size:15px;color:#4a3728;font-family:Arial,sans-serif;">
                {title}
              </td>
              <td style="padding:10px 0;border-bottom:1px solid #f0e8df;
                         font-size:15px;color:#4a3728;text-align:center;
                         font-family:Arial,sans-serif;">
                x{qty}
              </td>
              <td style="padding:10px 0;border-bottom:1px solid #f0e8df;
                         font-size:15px;color:#4a3728;text-align:right;
                         font-family:Arial,sans-serif;font-weight:600;">
                Rs. {float(price):,.0f}
              </td>
            </tr>"""

        total_pkr = total_cart_value
        items_html = f"""
        <table width="100%" cellpadding="0" cellspacing="0"
               style="margin:24px 0;border-collapse:collapse;">
          <thead>
            <tr>
              <th style="text-align:left;font-size:12px;color:#9a8878;
                         text-transform:uppercase;letter-spacing:1px;
                         padding-bottom:8px;border-bottom:2px solid #e8d5c4;
                         font-family:Arial,sans-serif;font-weight:600;">Item</th>
              <th style="text-align:center;font-size:12px;color:#9a8878;
                         text-transform:uppercase;letter-spacing:1px;
                         padding-bottom:8px;border-bottom:2px solid #e8d5c4;
                         font-family:Arial,sans-serif;font-weight:600;">Qty</th>
              <th style="text-align:right;font-size:12px;color:#9a8878;
                         text-transform:uppercase;letter-spacing:1px;
                         padding-bottom:8px;border-bottom:2px solid #e8d5c4;
                         font-family:Arial,sans-serif;font-weight:600;">Price</th>
            </tr>
          </thead>
          <tbody>{rows}</tbody>
          <tfoot>
            <tr>
              <td colspan="2" style="padding-top:12px;font-size:15px;
                                     color:#3a3028;font-weight:700;
                                     font-family:Arial,sans-serif;">Total</td>
              <td style="padding-top:12px;font-size:15px;color:#c9a96e;
                         font-weight:700;text-align:right;
                         font-family:Arial,sans-serif;">
                Rs. {total_pkr:,.0f}
              </td>
            </tr>
          </tfoot>
        </table>"""

    # Body paragraphs
    paragraphs = "".join(
        f'<p style="margin:0 0 16px 0;font-size:16px;line-height:1.75;'
        f'color:#4a3728;font-family:Arial,sans-serif;">{line.strip()}</p>'
        for line in body.split("\n") if line.strip()
        if not line.strip().startswith("Warmly") and not line.strip().startswith("Hi ")
        and not line.strip().startswith(SENDER_NAME)
    )

    year = datetime.utcnow().year

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1.0">
  <meta http-equiv="X-UA-Compatible" content="IE=edge">
  <title>{subject}</title>
  <!--[if mso]>
  <noscript><xml><o:OfficeDocumentSettings><o:PixelsPerInch>96</o:PixelsPerInch>
  </o:OfficeDocumentSettings></xml></noscript>
  <![endif]-->
</head>
<body style="margin:0;padding:0;background-color:#f5f0eb;
             -webkit-text-size-adjust:100%;-ms-text-size-adjust:100%;">

  <!-- Preheader (hidden preview text) -->
  <div style="display:none;max-height:0;overflow:hidden;
              color:#f5f0eb;font-size:1px;line-height:1px;">
    Hi {first_name}, your cart is waiting — use {discount_code} for 10% off today.
    &nbsp;&zwnj;&nbsp;&zwnj;&nbsp;&zwnj;&nbsp;&zwnj;&nbsp;&zwnj;
  </div>

  <table width="100%" cellpadding="0" cellspacing="0" border="0"
         style="background-color:#f5f0eb;min-width:320px;">
    <tr><td align="center" style="padding:32px 16px;">

      <!-- OUTER CARD -->
      <table width="580" cellpadding="0" cellspacing="0" border="0"
             style="max-width:580px;background:#ffffff;
                    border-radius:16px;overflow:hidden;
                    box-shadow:0 8px 40px rgba(0,0,0,0.10);">

        <!-- HEADER BANNER -->
        <tr>
          <td style="background:linear-gradient(135deg,#c9a96e 0%,#e8c99a 60%,#c9a96e 100%);
                     padding:36px 40px;text-align:center;">
            <p style="margin:0 0 6px 0;font-size:11px;color:rgba(255,255,255,0.75);
                      letter-spacing:4px;text-transform:uppercase;
                      font-family:Arial,sans-serif;font-weight:600;">
              EXCLUSIVE OFFER FOR YOU
            </p>
            <h1 style="margin:0;font-size:26px;color:#ffffff;
                       font-family:Georgia,serif;font-weight:700;
                       letter-spacing:2px;text-shadow:0 1px 3px rgba(0,0,0,0.15);">
              {SENDER_NAME.upper()}
            </h1>
          </td>
        </tr>

        <!-- GREETING BAND -->
        <tr>
          <td style="background:#fdf8f3;padding:20px 40px 0;
                     border-bottom:1px solid #f0e8df;">
            <p style="margin:0;font-size:22px;color:#3a3028;
                      font-family:Georgia,serif;font-weight:700;">
              Hi {first_name}, 👋
            </p>
            <p style="margin:6px 0 20px;font-size:13px;color:#9a8878;
                      font-family:Arial,sans-serif;">
              We saved your cart — it's still waiting for you.
            </p>
          </td>
        </tr>

        <!-- BODY CONTENT -->
        <tr>
          <td style="padding:28px 40px 8px;">
            {paragraphs}
            {items_html}
          </td>
        </tr>

        <!-- DISCOUNT CODE BOX -->
        <tr>
          <td style="padding:0 40px 28px;">
            <table width="100%" cellpadding="0" cellspacing="0" border="0">
              <tr>
                <td style="background:#fdf4e8;border:2px dashed #c9a96e;
                           border-radius:12px;padding:20px;text-align:center;">
                  <p style="margin:0 0 6px;font-size:12px;color:#9a8878;
                             text-transform:uppercase;letter-spacing:2px;
                             font-family:Arial,sans-serif;font-weight:600;">
                    YOUR EXCLUSIVE 10% OFF CODE
                  </p>
                  <p style="margin:0 0 4px;font-size:28px;font-weight:800;
                             color:#c9a96e;letter-spacing:5px;
                             font-family:Georgia,serif;">
                    {discount_code}
                  </p>
                  <p style="margin:0;font-size:12px;color:#b8a898;
                             font-family:Arial,sans-serif;">
                    Apply at checkout · One use only
                  </p>
                </td>
              </tr>
            </table>
          </td>
        </tr>

        <!-- CTA BUTTON -->
        <tr>
          <td style="padding:0 40px 36px;text-align:center;">
            <!--[if mso]>
            <v:roundrect xmlns:v="urn:schemas-microsoft-com:vml"
              href="{cart_link}" style="height:52px;v-text-anchor:middle;width:300px;"
              arcsize="10%" strokecolor="#c9a96e" fillcolor="#c9a96e">
              <w:anchorlock/>
              <center style="color:#ffffff;font-family:Arial,sans-serif;
                             font-size:16px;font-weight:700;">
                Complete My Purchase →
              </center>
            </v:roundrect>
            <![endif]-->
            <!--[if !mso]><!-->
            <a href="{cart_link}"
               style="display:inline-block;background:linear-gradient(135deg,#c9a96e,#b8935a);
                      color:#ffffff;text-decoration:none;font-size:16px;font-weight:700;
                      padding:16px 40px;border-radius:50px;
                      font-family:Arial,sans-serif;letter-spacing:0.5px;
                      box-shadow:0 4px 16px rgba(201,169,110,0.4);
                      transition:all 0.2s;">
              🛒 &nbsp;Complete My Purchase
            </a>
            <!--<![endif]-->
            <p style="margin:16px 0 0;font-size:12px;color:#b8a898;
                      font-family:Arial,sans-serif;">
              Having trouble? <a href="{cart_link}"
              style="color:#c9a96e;text-decoration:none;">{cart_link}</a>
            </p>
          </td>
        </tr>

        <!-- SIGN-OFF -->
        <tr>
          <td style="padding:24px 40px;background:#fdf8f3;
                     border-top:1px solid #f0e8df;">
            <p style="margin:0 0 4px;font-size:15px;color:#4a3728;
                      font-family:Arial,sans-serif;">
              With love,
            </p>
            <p style="margin:0;font-size:17px;font-weight:700;color:#3a3028;
                      font-family:Georgia,serif;">
              {SENDER_NAME} 💛
            </p>
          </td>
        </tr>

        <!-- FOOTER -->
        <tr>
          <td style="background:#f0e8df;padding:20px 40px;text-align:center;">
            <p style="margin:0 0 6px;font-size:12px;color:#9a8878;
                      font-family:Arial,sans-serif;line-height:1.5;">
              © {year} {SENDER_NAME}. All rights reserved.<br>
              You received this email because you left items in your cart.
            </p>
            <p style="margin:0;font-size:11px;color:#b8a898;
                      font-family:Arial,sans-serif;">
              <a href="mailto:{GMAIL_ADDRESS}?subject=unsubscribe"
                 style="color:#b8a898;text-decoration:underline;">Unsubscribe</a>
              &nbsp;·&nbsp;
              <a href="{SHOP_DOMAIN}"
                 style="color:#b8a898;text-decoration:underline;">Visit Our Store</a>
            </p>
          </td>
        </tr>

      </table>
      <!-- /OUTER CARD -->

    </td></tr>
  </table>
</body>
</html>"""


# ── Smoke test ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    result = send_email(
        to_email=GMAIL_ADDRESS,
        subject="Test: Your Sia Glow cart is waiting 💛",
        body="We noticed you left something special in your cart. We'd love to help you complete your purchase today.",
        cart_items=[{"title": "Rose Glow Serum", "quantity": 1, "price": 3499}],
        total_cart_value=3499,
        discount_code="SAVE10",
        customer_name="Ahmed",
    )
    print(result)

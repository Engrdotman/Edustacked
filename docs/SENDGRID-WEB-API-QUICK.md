# SendGrid Web API - Quick Implementation

**Setup time:** 15 minutes

---

## 1. Get API Key (5 minutes)

```
1. https://sendgrid.com → Sign up
2. Dashboard → Settings → API Keys
3. Create API Key (Full Access)
4. Copy key (starts with SG.)
```

---

## 2. Install Library (1 minute)

```bash
pip install sendgrid>=6.11,<7
```

Add to `backend/requirements.txt`:
```
sendgrid>=6.11,<7
```

---

## 3. Update settings.py (2 minutes)

In `backend/config/settings.py`, find the EMAIL section and replace:

```python
# OLD (SMTP)
EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST = "smtp.sendgrid.net"
EMAIL_HOST_USER = "apikey"
EMAIL_HOST_PASSWORD = os.getenv("SENDGRID_API_KEY", "")
EMAIL_PORT = 587
EMAIL_USE_TLS = True

# NEW (Web API) - REPLACE ABOVE WITH THIS:
EMAIL_BACKEND = "sendgrid_backend.SendgridBackend"
SENDGRID_API_KEY = os.getenv("SENDGRID_API_KEY", "")
SENDGRID_SANDBOX_MODE_IN_DEBUG = False

# Validation
if not DEBUG and not SENDGRID_API_KEY:
    raise ImproperlyConfigured("SENDGRID_API_KEY must be configured in production.")

DEFAULT_FROM_EMAIL = os.getenv("DEFAULT_FROM_EMAIL", "EDUstacked <noreply@yourdomain.com>")
```

---

## 4. Create Backend File (3 minutes)

Create `backend/apps/core/sendgrid_backend.py`:

```python
"""SendGrid Web API email backend for Django."""
from django.core.mail.backends.base import BaseEmailBackend
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail
from django.conf import settings


class SendgridBackend(BaseEmailBackend):
    """Django email backend using SendGrid Web API."""

    def __init__(self, fail_silently=False, **kwargs):
        super().__init__(fail_silently=fail_silently)
        self.client = SendGridAPIClient(settings.SENDGRID_API_KEY)

    def send_messages(self, email_messages):
        """Send emails and return count."""
        msg_count = 0
        for message in email_messages:
            try:
                msg = Mail(
                    from_email=message.from_email,
                    to_emails=message.to,
                    subject=message.subject,
                    plain_text_content=message.body,
                )
                # HTML content if available
                if hasattr(message, 'alternatives'):
                    for content, mimetype in message.alternatives:
                        if mimetype == 'text/html':
                            msg.html_content = content
                # CC, BCC
                if message.cc:
                    msg.cc = message.cc
                if message.bcc:
                    msg.bcc = message.bcc
                # Send
                self.client.send(msg)
                msg_count += 1
            except Exception as err:
                if not self.fail_silently:
                    raise
        return msg_count
```

---

## 5. Update .env (1 minute)

```
SENDGRID_API_KEY=SG.your-full-api-key-here
DEFAULT_FROM_EMAIL=EDUstacked <noreply@yourdomain.com>
```

---

## 6. Test Locally (2 minutes)

```bash
cd backend
python manage.py shell
```

```python
from django.core.mail import send_mail

send_mail(
    'Test',
    'It works!',
    'noreply@yourdomain.com',
    ['your-email@example.com'],
    fail_silently=False,
)
```

Check SendGrid dashboard → Activity

---

## 7. Deploy to Railway (1 minute)

Set Railway variables:
```
SENDGRID_API_KEY=SG.your-full-api-key-here
DEFAULT_FROM_EMAIL=EDUstacked <noreply@yourdomain.com>
```

Deploy and test signup.

---

## Verify Sender Email (3 minutes)

1. SendGrid Dashboard → Settings → Sender Authentication
2. "Verify a Single Sender"
3. Email: `noreply@yourdomain.com`
4. Verify the email link

---

## Done! ✅

Now using SendGrid Web API instead of SMTP.

**Why this is better:**
- ✅ More reliable
- ✅ Better error handling
- ✅ Built-in webhooks
- ✅ Easier to scale
- ✅ Better analytics

See `SENDGRID-WEB-API-SETUP.md` for advanced setup (webhooks, domain auth, etc.).

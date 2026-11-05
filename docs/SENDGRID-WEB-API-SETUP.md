# SendGrid Web API Setup for EDUstacked

This guide explains how to use SendGrid's Web API instead of SMTP. The Web API is **recommended for production** because it's:
- ✅ More reliable than SMTP
- ✅ Better error handling and bounce detection
- ✅ Built-in webhook support for delivery tracking
- ✅ Easier to scale without connection limits
- ✅ Better performance (no SMTP connection overhead)

---

## Why Web API Over SMTP?

| Feature | SMTP | Web API |
|---|---|---|
| Setup | Simple | Requires library |
| Reliability | Good | Better (HTTP) |
| Performance | Connection pooling | Native async |
| Error handling | Basic | Detailed |
| Webhooks | Not needed | Built-in |
| Rate limits | Connection limits | Request limits (higher) |
| Recommended | Testing | **Production** |

---

## Step 1: SendGrid Account & API Key

### Create SendGrid Account
1. Go to https://sendgrid.com
2. Click "Sign up"
3. Create account (free trial with $100 credit)
4. Verify your email
5. Log in to dashboard

### Generate API Key
1. **Left sidebar** → Settings → **API Keys**
2. Click **"Create API Key"**
3. **Name:** `EDUstacked Django Web API`
4. **Permissions:** Select "Full Access" (or custom if preferred)
5. Click **"Create & View"**
6. **Copy the entire key** (starts with `SG.`)
7. **Store it safely** (you can't view it again; you'll need to regenerate if lost)

---

## Step 2: Verify Sender Email/Domain

### Option A: Single Sender (Easiest)
1. **Left sidebar** → Settings → **Sender Authentication**
2. Click **"Verify a Single Sender"**
3. **From Email Address:** `noreply@yourdomain.com` or `edustacked@example.com`
4. Fill in other fields (name, reply-to, etc.)
5. Click **"Create"**
6. Check your email for verification link
7. Click the link to verify

### Option B: Domain Authentication (Better for Production)
1. **Left sidebar** → Settings → **Sender Authentication**
2. Click **"Verify a Domain"**
3. Enter your domain (e.g., `yourdomain.com`)
4. Add DNS records to your domain provider
5. Wait for verification (1–24 hours)
6. **Benefit:** All emails from that domain are authenticated (better deliverability)

---

## Step 3: Install SendGrid Python Library

### Install Package
```bash
cd backend
pip install sendgrid>=6.11,<7
```

### Update requirements.txt
```
sendgrid>=6.11,<7
```

---

## Step 4: Configure Django Email Backend

### Option A: Using SendGrid's Official Backend (Recommended)

#### Install SendGrid Django Extension
```bash
pip install sendgrid-django>=4.1,<5
```

#### Add to requirements.txt
```
sendgrid-django>=4.1,<5
```

#### Update settings.py

Add to `backend/config/settings.py`:

```python
# Email configuration - SendGrid Web API
EMAIL_BACKEND = "sendgrid_backend.SendgridBackend"
SENDGRID_API_KEY = os.getenv("SENDGRID_API_KEY", "")
SENDGRID_SANDBOX_MODE_IN_DEBUG = False  # Enable if you want to test without sending
SENDGRID_TRACK_EMAIL_OPENS = True
SENDGRID_TRACK_CLICKS = True

# Validation for production
if not DEBUG and not SENDGRID_API_KEY:
    raise ImproperlyConfigured("SENDGRID_API_KEY must be configured in production.")

DEFAULT_FROM_EMAIL = os.getenv("DEFAULT_FROM_EMAIL", "EDUstacked <noreply@yourdomain.com>")
```

#### Update .env (Local)
```
SENDGRID_API_KEY=SG.your-full-api-key-here
DEFAULT_FROM_EMAIL=EDUstacked <noreply@yourdomain.com>
```

---

### Option B: Using Django's HTTP Backend (Custom Implementation)

If you prefer not to add sendgrid-django, implement a custom backend:

#### Create `backend/apps/core/sendgrid_backend.py`

```python
"""SendGrid Web API email backend for Django."""
import json
from django.core.mail.backends.base import BaseEmailBackend
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail
from django.conf import settings


class SendGridBackend(BaseEmailBackend):
    """Django email backend using SendGrid Web API."""

    def __init__(self, fail_silently=False, **kwargs):
        super().__init__(fail_silently=fail_silently, **kwargs)
        self.client = SendGridAPIClient(settings.SENDGRID_API_KEY)

    def send_messages(self, email_messages):
        """Send one or more EmailMessage objects and return the number sent."""
        if not email_messages:
            return 0

        msg_count = 0
        for message in email_messages:
            try:
                self.send_message(message)
                msg_count += 1
            except Exception as err:
                if not self.fail_silently:
                    raise

        return msg_count

    def send_message(self, email_message):
        """Send a single EmailMessage using SendGrid Web API."""
        msg = Mail(
            from_email=email_message.from_email,
            to_emails=email_message.to,
            subject=email_message.subject,
            plain_text_content=email_message.body,
        )

        # Add HTML content if available
        if hasattr(email_message, 'alternatives'):
            for content, mimetype in email_message.alternatives:
                if mimetype == 'text/html':
                    msg.html_content = content
                    break

        # Add CC, BCC
        if email_message.cc:
            msg.cc = email_message.cc
        if email_message.bcc:
            msg.bcc = email_message.bcc

        # Add reply-to
        if email_message.reply_to:
            msg.reply_to = email_message.reply_to[0]

        # Send
        response = self.client.send(msg)
        return response
```

#### Update settings.py (Option B)

```python
EMAIL_BACKEND = "apps.core.sendgrid_backend.SendGridBackend"
SENDGRID_API_KEY = os.getenv("SENDGRID_API_KEY", "")

if not DEBUG and not SENDGRID_API_KEY:
    raise ImproperlyConfigured("SENDGRID_API_KEY must be configured in production.")

DEFAULT_FROM_EMAIL = os.getenv("DEFAULT_FROM_EMAIL", "EDUstacked <noreply@yourdomain.com>")
```

---

## Step 5: Local Testing

### Test with Django Shell
```bash
cd backend
python manage.py shell
```

```python
from django.core.mail import send_mail
from django.conf import settings

# Send test email
result = send_mail(
    subject='EDUstacked Test Email',
    message='If you receive this, SendGrid Web API is working!',
    from_email=settings.DEFAULT_FROM_EMAIL,
    recipient_list=['your-test-email@example.com'],
    fail_silently=False,
)

print(f"Email sent successfully: {result}")
```

### Check SendGrid Dashboard
1. Log in to SendGrid dashboard
2. Go to **Activity** or **Mail Send**
3. You should see the test email listed
4. Click on it to see delivery status

---

## Step 6: Railway Configuration

### Set Environment Variables

In **Railway backend service** → **Variables**, add:

```
SENDGRID_API_KEY=SG.your-full-api-key-here
DEFAULT_FROM_EMAIL=EDUstacked <noreply@yourdomain.com>
```

**Important:** 
- Use the full API key (starts with `SG.`)
- Mark SENDGRID_API_KEY as a **Secret** variable (not visible in logs)

### Optional: Webhooks (Advanced)

SendGrid can notify your app about delivery events (opens, clicks, bounces).

1. **SendGrid Dashboard** → Settings → **Mail Send Settings** → **Event Webhook**
2. Set webhook URL: `https://your-api.railway.app/api/v1/sendgrid/webhook/`
3. Select events: Delivered, Opened, Clicked, Bounced, Marked as Spam, Unsubscribed
4. Verify endpoint (SendGrid sends validation)

**Implement webhook handler** (optional):
```python
# backend/apps/billing/views.py or new apps/webhooks/views.py
from rest_framework.views import APIView
from rest_framework.response import Response
import json

class SendGridWebhookView(APIView):
    permission_classes = []  # Webhook is public
    
    def post(self, request):
        """Handle SendGrid event webhook."""
        events = json.loads(request.body) if isinstance(request.body, bytes) else request.data
        
        for event in events if isinstance(events, list) else [events]:
            event_type = event.get('event')
            email = event.get('email')
            
            if event_type == 'bounced':
                # Handle bounce (add to suppression list)
                pass
            elif event_type == 'marked_as_spam':
                # Handle spam complaint
                pass
        
        return Response({'status': 'ok'})
```

---

## Step 7: Production Deployment

### Pre-Deployment Checklist

- [ ] SendGrid account created and API key generated
- [ ] Sender email verified in SendGrid
- [ ] SendGrid Python library installed (`pip install sendgrid`)
- [ ] Django email backend configured (sendgrid_backend or custom)
- [ ] `.env` updated with SENDGRID_API_KEY (locally)
- [ ] settings.py updated with SENDGRID configuration
- [ ] SENDGRID_API_KEY set in Railway variables
- [ ] Test email sent successfully locally
- [ ] Test email received in inbox

### Deploy Steps

1. **Commit changes:**
   ```bash
   git add backend/requirements.txt backend/config/settings.py
   git commit -m "feat: configure SendGrid Web API for email"
   git push origin develop
   ```

2. **Set Railway variables:**
   - `SENDGRID_API_KEY=SG.your-key`
   - `DEFAULT_FROM_EMAIL=EDUstacked <noreply@yourdomain.com>`

3. **Deploy:**
   - Railway auto-deploys or manually trigger deploy
   - Monitor logs for any errors

4. **Test production:**
   - Create account on EDUstacked
   - Check for verification email
   - Verify it arrives within 30 seconds

---

## Troubleshooting

### "ModuleNotFoundError: No module named 'sendgrid'"
**Cause:** Library not installed  
**Fix:** `pip install sendgrid>=6.11,<7`

### "401 Unauthorized" or "Invalid API Key"
**Cause:** Wrong SENDGRID_API_KEY  
**Fix:** Verify API key is correct and starts with `SG.`

### Email not received
**Cause:** Multiple possibilities  
**Fix:**
1. Check SendGrid dashboard → Activity (did it send?)
2. Verify sender email is verified in SendGrid
3. Check spam folder
4. Check bounces/suppressions list

### "Sender email not verified"
**Cause:** From email not verified in SendGrid  
**Fix:** Verify sender in SendGrid Settings → Sender Authentication

### Email goes to spam
**Cause:** No domain verification  
**Fix:** Use Domain Authentication (DKIM/SPF) instead of single sender

---

## Monitoring & Analytics

### SendGrid Dashboard Features

1. **Activity:** Real-time email delivery status
2. **Stats:** Delivery, opens, clicks, bounces
3. **Suppressions:** Bounced emails, spam complaints, unsubscribes
4. **Contacts:** Manage recipient lists
5. **Webhooks:** Set up event notifications

### Setting Up Email Categories (Optional)

Tag different types of emails for tracking:
```python
msg.category = 'verification'  # or 'password-reset', 'notification', etc.
```

Then filter by category in SendGrid dashboard.

---

## Cost & Limits

| Plan | Price | Monthly Emails | Features |
|---|---|---|---|
| Free | $0 | 100 | Basic sending |
| Pro | $10+ | 200k+ | Analytics, webhooks, templates |
| Enterprise | Custom | Unlimited | Dedicated IP, compliance |

**For testing:** Free tier (100 emails/month)  
**For production:** Pro tier (~$0.10 per 1000 emails after free tier)

---

## Comparison: SMTP vs Web API

### SMTP (Current)
```python
# settings.py
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = 'smtp.sendgrid.net'
EMAIL_HOST_USER = 'apikey'
EMAIL_HOST_PASSWORD = 'SG.your-key'
EMAIL_PORT = 587
```

### Web API (Recommended)
```python
# settings.py
EMAIL_BACKEND = 'sendgrid_backend.SendgridBackend'
SENDGRID_API_KEY = 'SG.your-key'
```

**Advantages of Web API:**
- ✅ No SMTP connection management
- ✅ Better error messages
- ✅ Easier to implement webhooks
- ✅ Better for serverless/stateless environments
- ✅ Easier to scale

---

## Next Steps

1. **Choose implementation:** Official sendgrid-django or custom backend
2. **Install sendgrid library:** `pip install sendgrid>=6.11,<7`
3. **Update settings.py** (see above)
4. **Test locally** with Django shell
5. **Set Railway variables**
6. **Deploy and verify**
7. **Monitor** in SendGrid dashboard

---

## Resources

- [SendGrid Python Library](https://github.com/sendgrid/sendgrid-python)
- [SendGrid API Documentation](https://docs.sendgrid.com/api-reference/)
- [sendgrid-django](https://github.com/sendgrid/sendgrid-django)
- [Django Email Backends](https://docs.djangoproject.com/en/stable/topics/email/#email-backends)

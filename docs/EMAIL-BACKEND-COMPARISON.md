# Email Backend Comparison

## Quick Comparison

| Aspect | SMTP | Web API |
|---|---|---|
| **Setup Time** | 5 minutes | 15 minutes |
| **Complexity** | Simple | Medium |
| **Reliability** | Good | Better |
| **Error Info** | Basic | Detailed |
| **Webhooks** | No | Yes ✅ |
| **Rate Limits** | Connection-based | Request-based (higher) |
| **Scalability** | Limited | Excellent ✅ |
| **Production Ready** | Yes | Yes ✅ |
| **Recommended** | Testing | Production ✅ |

---

## SMTP Configuration

### How It Works
```
Django → SMTP Connection → SendGrid SMTP → Email Delivered
                 ↑
         (persistent connection)
```

### Setup
```python
# settings.py
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = 'smtp.sendgrid.net'
EMAIL_HOST_USER = 'apikey'
EMAIL_HOST_PASSWORD = 'SG.your-key'
EMAIL_PORT = 587
EMAIL_USE_TLS = True
```

### .env
```
SENDGRID_API_KEY=SG.your-key
```

### Pros
- ✅ Simple to set up
- ✅ Works with any mail provider
- ✅ Familiar (traditional SMTP)

### Cons
- ❌ Connection overhead
- ❌ Harder to scale
- ❌ Limited error info
- ❌ No native webhooks
- ❌ Can hit connection limits

### Best For
- Testing environments
- Low volume (< 1000 emails/day)

---

## Web API Configuration

### How It Works
```
Django → HTTP Request → SendGrid API → Email Delivered
         (stateless)
```

### Setup
```python
# settings.py
EMAIL_BACKEND = 'sendgrid_backend.SendgridBackend'
SENDGRID_API_KEY = 'SG.your-key'
```

### .env
```
SENDGRID_API_KEY=SG.your-key
```

### Pros
- ✅ Stateless (better for serverless)
- ✅ Better error messages
- ✅ Built-in webhooks
- ✅ Better rate limits
- ✅ Easier to scale
- ✅ Better for production

### Cons
- ❌ Requires library installation
- ❌ Slightly more setup
- ❌ SendGrid-specific (not generic SMTP)

### Best For
- **Production use** ✅
- High volume
- Advanced tracking needed
- Scaling requirements

---

## Migration Path: SMTP → Web API

### Current State (SMTP)
```python
# settings.py
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = 'smtp.sendgrid.net'
EMAIL_HOST_USER = 'apikey'
EMAIL_HOST_PASSWORD = os.getenv("SENDGRID_API_KEY")
EMAIL_PORT = 587
EMAIL_USE_TLS = True
```

### Step 1: Install Library
```bash
pip install sendgrid>=6.11,<7
```

### Step 2: Create Backend File
Save as `backend/apps/core/sendgrid_backend.py`:

```python
from django.core.mail.backends.base import BaseEmailBackend
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail
from django.conf import settings


class SendgridBackend(BaseEmailBackend):
    def __init__(self, fail_silently=False, **kwargs):
        super().__init__(fail_silently=fail_silently)
        self.client = SendGridAPIClient(settings.SENDGRID_API_KEY)

    def send_messages(self, email_messages):
        msg_count = 0
        for message in email_messages:
            try:
                msg = Mail(
                    from_email=message.from_email,
                    to_emails=message.to,
                    subject=message.subject,
                    plain_text_content=message.body,
                )
                if hasattr(message, 'alternatives'):
                    for content, mimetype in message.alternatives:
                        if mimetype == 'text/html':
                            msg.html_content = content
                if message.cc:
                    msg.cc = message.cc
                if message.bcc:
                    msg.bcc = message.bcc
                self.client.send(msg)
                msg_count += 1
            except Exception as err:
                if not self.fail_silently:
                    raise
        return msg_count
```

### Step 3: Update settings.py
**Replace:**
```python
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = 'smtp.sendgrid.net'
EMAIL_HOST_USER = 'apikey'
EMAIL_HOST_PASSWORD = os.getenv("SENDGRID_API_KEY")
EMAIL_PORT = 587
EMAIL_USE_TLS = True
```

**With:**
```python
EMAIL_BACKEND = 'apps.core.sendgrid_backend.SendgridBackend'
SENDGRID_API_KEY = os.getenv("SENDGRID_API_KEY", "")

if not DEBUG and not SENDGRID_API_KEY:
    raise ImproperlyConfigured("SENDGRID_API_KEY must be configured in production.")
```

### Step 4: Test
```bash
python manage.py shell
from django.core.mail import send_mail
send_mail('Test', 'Works!', 'noreply@yourdomain.com', ['test@example.com'])
```

### Step 5: Deploy
- Commit changes
- Push to GitHub
- Deploy to Railway (same SENDGRID_API_KEY variable works)

---

## Code Examples

### Sending a Basic Email (Both Work the Same)

```python
from django.core.mail import send_mail

send_mail(
    subject='Verification',
    message='Verify your email',
    from_email='noreply@yourdomain.com',
    recipient_list=['user@example.com'],
)
```

Works with both SMTP and Web API!

### Sending HTML Email

```python
from django.core.mail import EmailMultiAlternatives

msg = EmailMultiAlternatives(
    subject='Verification',
    body='Plain text',
    from_email='noreply@yourdomain.com',
    to=['user@example.com'],
)
msg.attach_alternative('<h1>Verification</h1>', 'text/html')
msg.send()
```

Works with both!

### Advanced: SendGrid-Specific Features (Web API Only)

```python
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail
from django.conf import settings

msg = Mail(
    from_email='noreply@yourdomain.com',
    to_emails='user@example.com',
    subject='Verification',
    plain_text_content='Verify your account',
    html_content='<h1>Verify Account</h1>',
)

# SendGrid-specific features
msg.category = 'verification'  # For tracking
msg.reply_to = 'support@yourdomain.com'

# Send
client = SendGridAPIClient(settings.SENDGRID_API_KEY)
response = client.send(msg)
```

Web API only!

---

## Decision Tree

```
Need to send emails?
│
├─ Testing environment?
│  └─ Use SMTP (simpler, no deps)
│
├─ Production, low volume (<1k/day)?
│  └─ Both work, SMTP is simpler
│
└─ Production, scale, webhooks needed?
   └─ Use Web API (recommended) ✅
```

---

## Monitoring & Tracking

### With SMTP
- Limited tracking
- Check SendGrid dashboard Activity tab

### With Web API + Webhooks
- Real-time event notifications
- Opens, clicks, bounces
- Implement webhook handler in Django
- Automatic suppression list management

---

## Cost

Both use same SendGrid plan:
- **Free tier:** 100 emails/month
- **Pro:** $10/month for 200k emails
- **Enterprise:** Custom pricing

No cost difference between SMTP and Web API.

---

## Recommendation

**For EDUstacked:**
- **Right now:** SMTP is fine (simpler, fewer dependencies)
- **When scaling:** Migrate to Web API (see migration path above)
- **For production:** Use Web API (better reliability, webhooks)

---

## See Also

- `SENDGRID-WEB-API-SETUP.md` — Detailed Web API setup
- `SENDGRID-WEB-API-QUICK.md` — Quick implementation
- `EMAIL-CONFIGURATION-GUIDE.md` — All email providers
- `QUICK-EMAIL-SETUP.md` — Copy-paste quick start

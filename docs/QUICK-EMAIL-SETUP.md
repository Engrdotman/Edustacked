# Quick Email Setup - Copy & Paste Guide

## For Testing (Gmail) - 5 Minutes

### Step 1: Gmail Account
- Email: `edustackedng@gmail.com` (or any Gmail)
- Password: secure password

### Step 2: Enable 2FA & App Password
```
1. Go to: https://myaccount.google.com/security
2. Click: 2-Step Verification
3. Follow steps, then go to: https://myaccount.google.com/apppasswords
4. Select Mail → Windows Computer
5. Copy the 16-character password
```

### Step 3: Local .env (Testing)
```
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_HOST_USER=edustackedng@gmail.com
EMAIL_HOST_PASSWORD=xxxx xxxx xxxx xxxx
EMAIL_USE_TLS=true
EMAIL_USE_SSL=false
DEFAULT_FROM_EMAIL=EDUstacked <edustackedng@gmail.com>
```

### Step 4: Test
```bash
cd backend
python manage.py shell
```
```python
from django.core.mail import send_mail
send_mail('Test', 'It works!', 'edustackedng@gmail.com', ['your@email.com'], fail_silently=False)
```

---

## For Production (SendGrid) - 10 Minutes

### Step 1: Create SendGrid Account
- Go to: https://sendgrid.com
- Sign up (free $100 credit)
- Verify email

### Step 2: Get API Key
```
1. Login to SendGrid
2. Left menu → Settings → API Keys
3. Click: Create API Key
4. Name: EDUstacked Django
5. Full Access
6. Create & View
7. Copy the key (starts with SG.)
```

### Step 3: Verify Sender Email
```
1. Left menu → Settings → Sender Authentication
2. Verify Single Sender
3. Email: noreply@yourdomain.com (or your Gmail)
4. Click verification link in your email
```

### Step 4: Railway Variables
```
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=smtp.sendgrid.net
EMAIL_PORT=587
EMAIL_HOST_USER=apikey
EMAIL_HOST_PASSWORD=SG.your-full-api-key-here
EMAIL_USE_TLS=true
EMAIL_USE_SSL=false
DEFAULT_FROM_EMAIL=EDUstacked <noreply@yourdomain.com>
```

### Step 5: Deploy & Test
- Set variables in Railway
- Deploy
- Signup on EDUstacked
- Check for verification email

---

## Provider Quick Reference

| Provider | Setup Time | Free | Setup Link | SMTP Host |
|---|---|---|---|---|
| **Gmail** | 5 min | ✅ Yes | myaccount.google.com | smtp.gmail.com |
| **SendGrid** | 10 min | ✅ $100 | sendgrid.com | smtp.sendgrid.net |
| **Mailgun** | 15 min | ❌ No | mailgun.com | smtp.mailgun.org |
| **AWS SES** | 20 min | ✅ 62k/mo | aws.amazon.com | email-smtp.*.amazonaws.com |

---

## Common Settings

**Port 587 (TLS):**
```
EMAIL_PORT=587
EMAIL_USE_TLS=true
EMAIL_USE_SSL=false
```

**Port 465 (SSL):**
```
EMAIL_PORT=465
EMAIL_USE_TLS=false
EMAIL_USE_SSL=true
```

---

## Verify It Works

**Local test:**
```bash
python manage.py shell
from django.core.mail import send_mail
send_mail('Test', 'Works!', 'from@example.com', ['to@example.com'])
```

**Production test:**
1. Signup on EDUstacked
2. Check inbox for verification email
3. Check spam folder if not found

---

## Troubleshooting

**"SMTPAuthenticationError"**
- Gmail: Using regular password? Use 16-char app password instead
- SendGrid: Using apikey as username? (not your email)

**"ConnectionRefusedError"**
- Wrong host? (smtp.gmail.com vs smtp.sendgrid.net)
- Wrong port? (usually 587)

**"Email doesn't arrive"**
- Check spam folder
- Verify sender email with provider
- Check provider's email logs/dashboard

---

## Full Guide

See `EMAIL-CONFIGURATION-GUIDE.md` for detailed info, all providers, and troubleshooting.

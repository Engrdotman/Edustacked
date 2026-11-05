# Email Configuration Guide for EDUstacked

This guide explains how to configure SMTP email for account verification, password resets, and notifications.

## Why Email is Required

Without email configuration:
- ❌ Users cannot verify their signup
- ❌ Password reset links don't arrive
- ❌ Notifications won't send
- ❌ Production deployment fails (Django validation enforces EMAIL_HOST_USER)

## Step 1: Choose an Email Provider

### Option 1: Gmail (Recommended for Testing)

**Advantages:**
- Free
- Simple setup
- Good for testing and small deployments

**Disadvantages:**
- Rate limited (sending quotas)
- Less suitable for high-volume production use
- Requires enabling "Less Secure Apps"

**Setup time:** 5 minutes

### Option 2: SendGrid (Recommended for Production)

**Advantages:**
- Affordable ($10–20/month for first 100,000 emails)
- Professional reputation tracking
- High deliverability
- Easy to scale
- Webhook support for advanced features

**Disadvantages:**
- Requires account creation and payment method
- Slightly more complex setup

**Setup time:** 10 minutes

### Option 3: Mailgun (Alternative Professional)

**Advantages:**
- Pay-per-use (cost-effective for small volume)
- Excellent API and logging
- Good for Nigeria

**Disadvantages:**
- Requires credit card
- Domain verification needed

**Setup time:** 15 minutes

### Option 4: Amazon SES (For High Volume)

**Advantages:**
- Very cheap at scale
- Integrates with AWS ecosystem
- Good deliverability

**Disadvantages:**
- Requires AWS account
- More complex setup

**Setup time:** 20 minutes

---

## Configuration by Provider

### **Gmail Setup (Simplest for Testing)**

1. **Create or use a Gmail account:**
   - Email: `edustackedng@gmail.com` (or your choice)
   - Password: Something secure

2. **Enable 2-Factor Authentication:**
   - Go to [Google Account Security](https://myaccount.google.com/security)
   - Click "2-Step Verification"
   - Follow the steps

3. **Create an App Password:**
   - Go to [Google App Passwords](https://myaccount.google.com/apppasswords)
   - Select "Mail" and "Windows Computer" (or your system)
   - Click "Generate"
   - Copy the 16-character password (Gmail generates this; not your regular password)

4. **Use these settings in Railway (or local .env):**
   ```
   EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
   EMAIL_HOST=smtp.gmail.com
   EMAIL_PORT=587
   EMAIL_HOST_USER=edustackedng@gmail.com
   EMAIL_HOST_PASSWORD=xxxx xxxx xxxx xxxx  (the 16-char app password)
   EMAIL_USE_TLS=true
   EMAIL_USE_SSL=false
   DEFAULT_FROM_EMAIL=EDUstacked <edustackedng@gmail.com>
   ```

5. **Test locally:**
   ```bash
   cd backend
   python manage.py shell
   
   # In the Python shell:
   from django.core.mail import send_mail
   send_mail(
       'Test Email',
       'If you receive this, email is working!',
       'edustackedng@gmail.com',
       ['your-test-email@example.com'],
       fail_silently=False,
   )
   ```

   If it works, you'll receive the test email.

---

### **SendGrid Setup (Recommended for Production)**

1. **Create SendGrid Account:**
   - Go to [sendgrid.com](https://sendgrid.com)
   - Sign up (free trial includes $100 credit)
   - Verify your email
   - Log in to dashboard

2. **Create an API Key:**
   - Left menu → Settings → API Keys
   - Click "Create API Key"
   - Name: `EDUstacked Django`
   - Permissions: Full Access (for now)
   - Click "Create & View"
   - Copy the key (starts with `SG.`)

3. **Verify Sender Email:**
   - Left menu → Settings → Sender Authentication
   - Choose "Verify a Single Sender"
   - Enter: `noreply@yourdomain.com` (or use `edustackedng@gmail.com` if no domain)
   - Verify the email by clicking the link SendGrid sends

4. **Use these settings in Railway:**
   ```
   EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
   EMAIL_HOST=smtp.sendgrid.net
   EMAIL_PORT=587
   EMAIL_HOST_USER=apikey
   EMAIL_HOST_PASSWORD=SG.your-api-key-here
   EMAIL_USE_TLS=true
   EMAIL_USE_SSL=false
   DEFAULT_FROM_EMAIL=EDUstacked <noreply@yourdomain.com>
   ```

5. **Test in Railway:**
   - Set the variables
   - Deploy
   - Trigger a signup and verify email arrives

---

### **Mailgun Setup**

1. **Create Mailgun Account:**
   - Go to [mailgun.com](https://mailgun.com)
   - Sign up
   - Add a payment method (pay-per-use)

2. **Get SMTP Credentials:**
   - Dashboard → Sending → Domain Settings
   - Select your domain
   - SMTP > SMTP Credentials
   - Copy the SMTP login and password

3. **Use these settings in Railway:**
   ```
   EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
   EMAIL_HOST=smtp.mailgun.org
   EMAIL_PORT=587
   EMAIL_HOST_USER=postmaster@yourdomain.mailgun.org
   EMAIL_HOST_PASSWORD=your-mailgun-password
   EMAIL_USE_TLS=true
   EMAIL_USE_SSL=false
   DEFAULT_FROM_EMAIL=EDUstacked <noreply@yourdomain.mailgun.org>
   ```

---

### **Amazon SES Setup (Advanced)**

Requires AWS account and IAM user setup. See AWS documentation for SMTP credentials.

Common settings:
```
EMAIL_HOST=email-smtp.eu-west-1.amazonaws.com  (use your region)
EMAIL_PORT=587
EMAIL_HOST_USER=AKIA...  (IAM user access key)
EMAIL_HOST_PASSWORD=  (IAM user secret key)
EMAIL_USE_TLS=true
```

---

## Local Development (.env File)

For testing locally, create/update `backend/.env`:

```
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_HOST_USER=your-email@gmail.com
EMAIL_HOST_PASSWORD=your-16-char-app-password
EMAIL_USE_TLS=true
DEFAULT_FROM_EMAIL=EDUstacked <your-email@gmail.com>
```

Then restart your local Django server:
```bash
cd backend
python manage.py runserver
```

---

## Troubleshooting Email Issues

### "SMTPAuthenticationError"
**Cause:** Wrong password or credentials  
**Fix:** Double-check EMAIL_HOST_USER and EMAIL_HOST_PASSWORD  
**Gmail:** Use the 16-character app password, not your regular password

### "SMTPServerDisconnected"
**Cause:** Wrong EMAIL_PORT or EMAIL_USE_TLS/EMAIL_USE_SSL settings  
**Fix:** Verify port (usually 587 for TLS) and TLS/SSL settings

### "ConnectionRefusedError"
**Cause:** EMAIL_HOST is unreachable  
**Fix:** Verify EMAIL_HOST is correct (e.g., smtp.gmail.com, smtp.sendgrid.net)

### "Email doesn't arrive"
**Cause:** Email is going to spam or wrong address  
**Fix:**
1. Check spam folder
2. Verify DEFAULT_FROM_EMAIL is a verified sender
3. Check SMTP provider's email logs (SendGrid dashboard shows delivery status)

### Production deployment fails with "EMAIL_HOST_USER must be configured"
**Cause:** DJANGO_DEBUG=false but EMAIL_HOST_USER not set  
**Fix:** In Railway backend variables, set EMAIL_HOST_USER (this triggers production validation)

---

## Testing Email After Configuration

### Method 1: Django Shell
```bash
cd backend
python manage.py shell
```

```python
from django.core.mail import send_mail

result = send_mail(
    'EDUstacked Test Email',
    'This is a test. If you see this, email is working!',
    'edustackedng@gmail.com',  # From address
    ['your-personal-email@example.com'],  # To address
    fail_silently=False,
)
print(f"Email sent: {result}")
```

If `result` is `1`, email was sent. Check your inbox (or spam folder).

### Method 2: Trigger Signup
1. Go to the EDUstacked signup page
2. Register with an email address
3. Check if verification email arrives within 30 seconds

---

## Production Checklist

Before launching on Railway:

- [ ] Email provider account created (Gmail, SendGrid, etc.)
- [ ] SMTP credentials obtained and verified
- [ ] Sender email address verified with provider (if required)
- [ ] EMAIL_HOST_USER set in Railway variables
- [ ] EMAIL_HOST_PASSWORD set in Railway variables (use secret)
- [ ] EMAIL_HOST set correctly
- [ ] EMAIL_PORT set correctly
- [ ] EMAIL_USE_TLS or EMAIL_USE_SSL configured correctly
- [ ] DEFAULT_FROM_EMAIL set to a verified sender
- [ ] Test email sent successfully from Railway
- [ ] Signup verification email received
- [ ] Password reset email tested

---

## Cost Estimates

| Provider | Free/Month | Usage | Cost |
|---|---|---|---|
| Gmail | ∞* | 500 emails/day max | Free (limited) |
| SendGrid | 100 free emails | Pay-as-you-go after | $0–20 for 100k emails |
| Mailgun | 0 (paid only) | Pay-as-you-go | ~$0.50 per 1000 emails |
| Amazon SES | 62,000 emails/month** | Pay-as-you-go | $0.10 per 1000 emails |

*Gmail requires manual intervention beyond 500/day  
**Only for email sent to verified addresses; outbound only

---

## Advanced Configuration

### Custom Domain Email

Use your own domain (e.g., noreply@yourdomain.com):

1. Verify domain with your email provider (DNS TXT records)
2. Use provider's SMTP settings
3. Set `DEFAULT_FROM_EMAIL=EDUstacked <noreply@yourdomain.com>`

This improves email deliverability and branding.

### Monitoring Email Delivery

SendGrid and Mailgun provide delivery tracking:
- Click rates, bounce rates, spam complaints
- Use for debugging delivery issues
- Check provider dashboard after configuration

### Fallback Email Address

Set a fallback email for critical alerts:
```python
# In settings.py (not yet implemented)
ADMINS = [('EDUstacked', 'admin@yourdomain.com')]
```

Errors will be emailed to this address in production.

---

## Next Steps

1. **Local testing:** Configure email in `.env`, test with Django shell
2. **Deploy to Railway:** Set EMAIL_* variables, verify startup logs
3. **Integration testing:** Create account, check verification email
4. **Monitor:** Check provider dashboard for delivery status

Questions? See `railway-deployment-checklist.md` for full Railway setup.

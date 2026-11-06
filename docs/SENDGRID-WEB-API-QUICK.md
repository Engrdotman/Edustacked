# SendGrid Web API setup

The project includes a Django email backend that uses SendGrid's Web API. It
does not use SendGrid SMTP. The backend path is
`apps.core.sendgrid_backend.SendgridBackend`.

## Local development

Install backend dependencies from `backend/`:

```shell
pip install -r requirements.txt
```

In the ignored `backend/.env` file, set:

```dotenv
EMAIL_BACKEND=apps.core.sendgrid_backend.SendgridBackend
SENDGRID_API_KEY=SG.your-secret-api-key
SENDGRID_SANDBOX_MODE=false
DEFAULT_FROM_EMAIL="EDUstacked <edustackedng@gmail.com>"
```

Keep the API key out of source control. `backend/.env.example` documents these
variables without enabling external email delivery by default. To capture
development email locally instead, remove `EMAIL_BACKEND` from `.env` or set
it to `django.core.mail.backends.locmem.EmailBackend`.

## Production deployment

Set `EMAIL_BACKEND`, `SENDGRID_API_KEY`, `SENDGRID_SANDBOX_MODE=false`, and
`DEFAULT_FROM_EMAIL` as service environment variables (Railway Variables, for
example). SendGrid requires a valid API key with Mail Send permission and a
verified sender identity. Use the same verified address/domain in
`DEFAULT_FROM_EMAIL`. Do not set SMTP credentials when using the Web API.

If the backend is selected without an API key, Django fails configuration
early with a clear error. The backend checks SendGrid's HTTP status and raises
on rejected sends so verification and password-reset requests cannot appear to
succeed when SendGrid rejected them. Set `SENDGRID_SANDBOX_MODE=true` only for
an API validation run; sandbox acceptance does not deliver the email.

## Safe local validation

Check Django's selected backend without sending email:

```shell
python manage.py shell -c "from django.conf import settings; print(settings.EMAIL_BACKEND); print(bool(settings.SENDGRID_API_KEY))"
```

To verify actual delivery, send a message only to an address you control, then
check SendGrid's Email Activity. Never print or paste the API key into logs or
support messages.

"""Django email backend that sends messages through SendGrid's Web API."""

import base64

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.core.mail.backends.base import BaseEmailBackend
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import (
    Attachment,
    Bcc,
    Cc,
    Disposition,
    FileContent,
    FileName,
    FileType,
    Header,
    Mail,
    MailSettings,
    Personalization,
    SandBoxMode,
    To,
)


class SendgridBackend(BaseEmailBackend):
    """Send Django EmailMessage instances through SendGrid's v3 API."""

    def __init__(self, fail_silently=False, **kwargs):
        super().__init__(fail_silently=fail_silently)
        api_key = getattr(settings, "SENDGRID_API_KEY", "").strip()
        if not api_key:
            raise ImproperlyConfigured(
                "SENDGRID_API_KEY is required when using the SendGrid email backend."
            )
        self.client = SendGridAPIClient(api_key=api_key)

    def _build_mail(self, message):
        mail = Mail(
            from_email=message.from_email,
            subject=message.subject,
            plain_text_content=message.body if not message.content_subtype == "html" else None,
            html_content=message.body if message.content_subtype == "html" else None,
        )

        personalization = Personalization()
        for recipient in message.to or []:
            personalization.add_to(To(recipient))
        for recipient in message.cc or []:
            personalization.add_cc(Cc(recipient))
        for recipient in message.bcc or []:
            personalization.add_bcc(Bcc(recipient))
        if message.to or message.cc or message.bcc:
            mail.add_personalization(personalization)

        for content, mimetype in getattr(message, "alternatives", []):
            if mimetype == "text/html":
                mail.add_content(content, mimetype)

        if message.reply_to:
            mail.reply_to = message.reply_to[0]

        for name, value in (message.extra_headers or {}).items():
            mail.add_header(Header(name, str(value)))

        for attachment in message.attachments or []:
            if isinstance(attachment, tuple):
                filename, content, mimetype = attachment
                if isinstance(content, str):
                    content = content.encode("utf-8")
                content_type = mimetype or "application/octet-stream"
            else:
                filename = getattr(attachment, "name", "attachment")
                content = attachment.as_bytes()
                content_type = attachment.get_content_type()

            encoded_content = base64.b64encode(content).decode("ascii")
            mail.add_attachment(
                Attachment(
                    FileContent(encoded_content),
                    FileName(filename),
                    FileType(content_type),
                    Disposition("attachment"),
                )
            )

        if getattr(settings, "SENDGRID_SANDBOX_MODE", False):
            mail_settings = MailSettings()
            mail_settings.sandbox_mode = SandBoxMode(True)
            mail.mail_settings = mail_settings

        return mail

    def send_messages(self, email_messages):
        sent_count = 0
        for message in email_messages:
            try:
                response = self.client.send(self._build_mail(message))
                if not 200 <= response.status_code < 300:
                    raise RuntimeError(
                        f"SendGrid rejected the email with HTTP {response.status_code}."
                    )
                sent_count += 1
            except Exception:
                if not self.fail_silently:
                    raise
        return sent_count

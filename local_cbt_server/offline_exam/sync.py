from datetime import timedelta
import hmac
import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .models import LocalExamSession, SyncLog, SyncOutbox
from .services import canonical_json, finalize_session


def process_due_outbox(limit=None):
    # When the worker is running, persist timeout submissions even if no
    # candidate is making requests. On restart, any already-created outbox row
    # is still delivered normally.
    expired = LocalExamSession.objects.filter(
        status=LocalExamSession.Status.IN_PROGRESS, expires_at__lte=timezone.now()
    ).values_list("pk", flat=True)[: settings.LOCAL_CBT_SYNC_BATCH_SIZE]
    for session_id in expired:
        finalize_session(LocalExamSession.objects.get(pk=session_id), auto=True)
    if not settings.CENTRAL_SYNC_URL or not settings.CENTRAL_SYNC_TOKEN:
        return {"attempted": 0, "synced": 0, "failed": 0, "expired_submissions": len(expired), "configuration_error": "Central sync URL/token are not configured."}
    limit = limit or settings.LOCAL_CBT_SYNC_BATCH_SIZE
    rows = list(SyncOutbox.objects.filter(status=SyncOutbox.Status.PENDING, next_attempt_at__lte=timezone.now()).order_by("created_at")[:limit])
    synced = 0
    failed = 0
    for row in rows:
        raw = canonical_json(row.payload)
        envelope = {
            "payload": row.payload,
            "payload_hash": row.payload_hash,
            "signature": hmac.new(settings.CENTRAL_SYNC_TOKEN.encode("utf-8"), raw, "sha256").hexdigest(),
        }
        row.last_attempt_at = timezone.now()
        row.retry_count += 1
        row.save(update_fields=("last_attempt_at", "retry_count"))
        try:
            request = Request(
                f"{settings.CENTRAL_SYNC_URL}/api/v1/cbt/sync/ingest/",
                data=json.dumps(envelope).encode("utf-8"),
                headers={"Authorization": f"Bearer {settings.CENTRAL_SYNC_TOKEN}", "Content-Type": "application/json"},
                method="POST",
            )
            # Certificate verification is enabled by default in urllib. The
            # explicit disable switch is retained only for isolated lab setups.
            import ssl
            context = None if settings.CENTRAL_SYNC_VERIFY_TLS else ssl._create_unverified_context()
            with urlopen(request, timeout=20, context=context) as response:
                response_status = response.status
                response_body = response.read().decode("utf-8", errors="replace")
            if 200 <= response_status < 300 and json.loads(response_body).get("accepted"):
                row.status = SyncOutbox.Status.SYNCED
                row.synced_at = timezone.now()
                row.error_detail = ""
                row.save(update_fields=("status", "synced_at", "error_detail"))
                SyncLog.objects.create(event_id=row.event_id, action="sync", status="synced", detail="Central API accepted the submission.")
                synced += 1
                continue
            error = response_body[:800] or f"Central API returned HTTP {response_status}."
        except HTTPError as exc:
            error = f"Central API returned HTTP {exc.code}: {exc.read().decode('utf-8', errors='replace')[:700]}"
        except (URLError, TimeoutError, OSError) as exc:
            error = f"Central API is unreachable: {exc}"[:800]
        except (ValueError, AttributeError) as exc:
            error = f"Central API returned an invalid response: {exc}"[:800]

        row.error_detail = error
        if row.retry_count >= settings.LOCAL_CBT_MAX_SYNC_RETRIES:
            row.status = SyncOutbox.Status.FAILED
            row.save(update_fields=("status", "error_detail"))
            SyncLog.objects.create(event_id=row.event_id, action="sync", status="failed", detail=error)
            failed += 1
            continue
        delay_minutes = min(60, 2 ** min(row.retry_count - 1, 6))
        row.next_attempt_at = timezone.now() + timedelta(minutes=delay_minutes)
        row.save(update_fields=("next_attempt_at", "error_detail"))
        SyncLog.objects.create(event_id=row.event_id, action="retry", status="pending", detail=error)
        failed += 1
    return {"attempted": len(rows), "synced": synced, "failed": failed, "expired_submissions": len(expired)}

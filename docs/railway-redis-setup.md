# Connect Railway Redis to EDUstacked

EDUstacked already supports Redis through Django's cache backend. Redis is an optional shared cache; it does not store student records and does not replace PostgreSQL.

## Set it up in Railway

1. Open the EDUstacked Railway project and choose **New → Database → Redis**. Keep Redis private inside the project.
2. Open the Django backend service, then **Variables**.
3. Add a reference variable named `REDIS_URL` with this value, replacing `Redis` if you named the service differently:

   ```text
   ${{Redis.REDIS_URL}}
   ```

4. Make sure the variable is added to the **Edustacked backend service** in the same Railway environment as the running deployment, then redeploy. Do not add this variable to Netlify or Vercel; it is server-side only.
5. After deployment, open `https://edustacked-production.up.railway.app/api/v1/health/`. The response now reports cache status without exposing the Redis URL:

   - `"backend": "redis", "status": "connected"` means Django can read and write Redis.
   - `"backend": "local-memory"` means `REDIS_URL` is not present on the running backend deployment.
   - `"backend": "redis", "status": "unavailable"` means Django sees the URL but cannot reach Redis. Check that Redis is online, both services are in the same Railway environment, and the reference points to the Redis service's `REDIS_URL`.

6. If you have access to the backend service shell, you can also confirm the cache directly:

   ```bash
   python manage.py shell -c "from django.conf import settings; from django.core.cache import cache; cache.set('redis_check', 'ok', 30); print(settings.CACHES['default']['BACKEND'], cache.get('redis_check'))"
   ```

   A successful check prints Django's Redis cache backend and `ok`. Do not paste the Redis URL or its password into logs, GitHub, or chat.

## What changes when Redis is enabled

- Django uses `django.core.cache.backends.redis.RedisCache` when `REDIS_URL` is present.
- Without `REDIS_URL`, Django falls back to local-memory cache. That is fine for local development and a single process, but each backend worker or instance has a separate cache.
- Shared cache is useful for API rate limits and cache entries when multiple Gunicorn workers or Railway instances serve requests.
- PostgreSQL remains the durable database. Redis cache entries are disposable and can be rebuilt; an outage may temporarily affect endpoints that depend on the shared cache or throttling.

## If the connection check fails

- Confirm the variable is named exactly `REDIS_URL` on the backend service.
- Confirm the Railway variable reference uses the exact Redis service name and `REDIS_URL` output.
- Keep the Redis and backend services in the same Railway project/environment and use the private reference, not a public URL.
- Redeploy the backend after changing variables, then inspect backend deployment logs for a Redis connection error.

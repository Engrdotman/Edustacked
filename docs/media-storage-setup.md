# Durable Media Storage

## What is stored where

- Frontend JavaScript, CSS, and bundled images are built into `frontend/dist/` and served by the Render frontend service.
- Django static assets are collected to `backend/staticfiles/` and served with WhiteNoise.
- School uploads such as logos and principal signatures use Django's default file storage. Without a bucket configured, that storage is `backend/media/`, which is suitable only for local development and can disappear when the backend container is replaced.

The backend now supports a private S3-compatible object-storage bucket. Logo and signature download routes continue to pass through Django's school authorization checks; the bucket does not need public access or browser CORS rules. The report-card renderer reads image files through Django's storage API.

## Configure the backend

Choose an S3-compatible object store, create a private bucket and a restricted access key, then add these variables to the **Railway backend service**:

```text
AWS_STORAGE_BUCKET_NAME=edustacked-media
AWS_S3_ENDPOINT_URL=https://<account-id>.r2.cloudflarestorage.com
AWS_S3_REGION_NAME=auto
AWS_ACCESS_KEY_ID=<storage-access-key>
AWS_SECRET_ACCESS_KEY=<storage-secret>
AWS_MEDIA_LOCATION=media
```

For Amazon S3, leave `AWS_S3_ENDPOINT_URL` unset and use the bucket's actual region instead of `auto`. Keep the secret key only in Railway's secret variables. Do not place these values in the frontend or commit them to GitHub.

The backend requirements include `django-storages[s3]`. When `AWS_STORAGE_BUCKET_NAME` is set, Django uses the bucket for uploaded files. When it is unset, local development and CI continue to use `MEDIA_ROOT`.

## Preserve existing uploads

Before the next backend redeploy, save a copy of any logo or signature currently visible in the school profile. App-container media may be ephemeral. If an existing Railway volume is mounted at the current media directory, keep it mounted until files are copied.

After the storage settings have deployed and the bucket variables are active, open the Railway backend shell and run this first:

```bash
python manage.py migrate_media_to_storage --dry-run
```

If it reports files to copy, run:

```bash
python manage.py migrate_media_to_storage
```

This copies files using their existing storage names and skips files already in the bucket. It does not change database records or delete local copies. If the old container's files were already lost, upload the saved logo and signature again through the school profile page.

After copying, verify the school profile still shows the logo/signature and generate a report-card preview. Keep the bucket private; the application serves authorized files through its API.

# Deploy V28

Repo này chứa cả frontend Cloudflare và backend Flask Render.

## GitHub

```powershell
git add .
git commit -m "upgrade postgres r2"
git push
```

## Cloudflare Pages

- Production branch: `main`
- Framework preset: `None`
- Build command: `exit 0`
- Build output directory: `public`
- Variable: `BACKEND_ORIGIN=https://tap-hoa-delta-force-api.onrender.com`
- R2 binding: `MEDIA` → bucket `tap-hoa-delta-force-media`

## Render Flask

- Build: `pip install -r requirements.txt`
- Start: `gunicorn app:application --bind 0.0.0.0:$PORT --workers 1 --threads 4 --timeout 120`
- Thêm `DATABASE_URL` và 4 biến R2 theo `README_RENDER_CLOUDFLARE.md`.

## Trước khi đổi database

Nếu SQLite hiện tại đã có dữ liệu thật, vào Admin tải Backup trước. Có thể dùng `migrate_backup_to_postgres_r2.py` để nhập backup V27 vào PostgreSQL + R2.

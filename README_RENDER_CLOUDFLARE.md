# Tạp Hóa Delta Force — Render + Cloudflare V28

## Production

- Cloudflare Pages: frontend + admin + Pages Functions
- Render Web Service: Flask API
- Render PostgreSQL: dữ liệu bền vững
- Cloudflare R2: ảnh acc / ảnh chi tiết / ảnh giftcode

## Render Web Service

- Build command: `pip install -r requirements.txt`
- Start command: `gunicorn app:application --bind 0.0.0.0:$PORT --workers 1 --threads 4 --timeout 120`
- Branch: `main`
- Root directory: để trống

Environment:

```text
SHOP_HTTPS=1
SHOP_SECRET_KEY=<secret dài>
SHOP_ADMIN_PASSWORD=<mật khẩu admin >= 12 ký tự>
DATABASE_URL=<Render Postgres Internal Database URL>
R2_ACCOUNT_ID=<Cloudflare account id>
R2_BUCKET=tap-hoa-delta-force-media
R2_ACCESS_KEY_ID=<R2 Access Key ID>
R2_SECRET_ACCESS_KEY=<R2 Secret Access Key>
```

## Cloudflare Pages

Build:

```text
Framework preset: None
Build command: exit 0
Build output directory: public
Root directory: để trống
```

Variables:

```text
BACKEND_ORIGIN=https://tap-hoa-delta-force-api.onrender.com
```

Bindings:

```text
Type: R2 bucket
Variable name: MEDIA
Bucket: tap-hoa-delta-force-media
```

Redeploy sau khi thêm hoặc thay đổi Variables/Bindings.

## Health check

`/healthz` kiểm tra cả kết nối database. Khi production đúng:

```json
{"ok":true,"database":"postgres","images":"r2"}
```

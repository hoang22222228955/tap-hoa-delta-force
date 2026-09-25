# V28 — PostgreSQL + Cloudflare R2

Bản này thay lớp lưu trữ production nhưng giữ nguyên giao diện/API hiện tại.

## Kiến trúc

- Frontend/Admin: Cloudflare Pages
- API: Render Flask
- Database production: Render PostgreSQL qua `DATABASE_URL`
- Ảnh upload: Cloudflare R2
- Ảnh public: Cloudflare Pages Function đọc trực tiếp binding R2 `MEDIA`
- Local/offline fallback: SQLite + thư mục `images/`

## Biến môi trường Render

Giữ các biến cũ:

- `SHOP_HTTPS=1`
- `SHOP_SECRET_KEY=...`
- `SHOP_ADMIN_PASSWORD=...`

Thêm:

- `DATABASE_URL` = Render Postgres **Internal Database URL**
- `R2_ACCOUNT_ID`
- `R2_BUCKET=tap-hoa-delta-force-media`
- `R2_ACCESS_KEY_ID`
- `R2_SECRET_ACCESS_KEY`

Nếu có `DATABASE_URL` thì app dùng PostgreSQL. Nếu không có thì dùng SQLite.
Nếu đủ 4 biến R2 thì app upload ảnh vào R2. Nếu không có biến R2 nào thì app dùng ảnh local.
Nếu chỉ điền một phần biến R2, app chủ động báo lỗi cấu hình thay vì âm thầm lưu nhầm vào ổ tạm.

## Cloudflare Pages

Trong project `tap-hoa-delta-force`:

1. Settings → Bindings → Add → R2 bucket
2. Variable name: `MEDIA`
3. Bucket: `tap-hoa-delta-force-media`
4. Save và redeploy

`functions/images/[[path]].js` sẽ đọc ảnh trực tiếp từ R2. Nếu binding chưa có hoặc object chưa có, nó fallback sang Render.

## Kiểm tra

Render:

`https://tap-hoa-delta-force-api.onrender.com/healthz`

Production đúng sẽ trả gần như:

```json
{"ok":true,"database":"postgres","images":"r2"}
```

Cloudflare:

`https://tap-hoa-delta-force.pages.dev/api/healthz`

Sau đó upload thử một ảnh trong Admin và kiểm tra URL dạng:

`https://tap-hoa-delta-force.pages.dev/images/<32-hex>.webp`

## Di chuyển dữ liệu SQLite cũ

Trước khi đổi backend production, tải `Backup` từ Admin V27. ZIP backup cũ có `database.sqlite3` và thư mục `images/`.

Bản V28 kèm script:

`migrate_backup_to_postgres_r2.py`

Script này xóa dữ liệu hiện tại trong PostgreSQL đích rồi nhập dữ liệu từ backup, sau đó upload ảnh backup lên R2. Chỉ chạy nếu cần giữ dữ liệu cũ.

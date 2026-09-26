# Audit V28

- PostgreSQL support qua `DATABASE_URL`, SQLite vẫn dùng được local.
- SQL adapter giữ nguyên API/query hiện có và tương thích bind parameters PostgreSQL.
- PostgreSQL schema có đầy đủ bảng/column V27 và thứ tự record riêng cho các danh sách admin.
- R2 upload dùng S3-compatible API bằng boto3.
- Cloudflare Pages `/images/*` ưu tiên đọc trực tiếp R2 binding `MEDIA`, fallback Render.
- Ảnh vẫn lưu reference `images/<uuid>.webp`, không phá dữ liệu frontend/admin hiện tại.
- Backup PostgreSQL xuất `database.json`; backup SQLite vẫn xuất `database.sqlite3`.
- Có script di chuyển backup V27 SQLite + images sang PostgreSQL + R2.
- Python syntax: checked.
- Pages Functions JS syntax: checked.

## V30
- Added per-product/service `zalo_phone` with additive DB migration.
- Added dedicated service dossier modal with gallery and item-specific Zalo routing.
- Added visible Zalo quick suggestions in Admin product/service editor.

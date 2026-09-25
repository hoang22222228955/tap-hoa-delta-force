# Audit v26

## Giữ lại trong `public/`
Các trang đang dùng: `index.html`, `kho-acc.html`, `dich-vu.html`, `giftcode.html`, `tin-tuc.html`, cùng `catalog.js`, favicon và asset CSS/JS/ảnh cần thiết.

## Không đưa vào bản Cloudflare public
- Backend/local admin: `app.py`, `admin.html`, `restore_backup.py`, `requirements.txt`, các file `.bat/.sh`.
- Dữ liệu runtime: SQLite/session key trong `data/` (không được commit lên GitHub).
- Ảnh atlas cũ `images/models.png`, `images/prints.png`: catalogue hiện tại không sử dụng trong bản static.

## Các file legacy/trùng đã loại
- `products.html`, `market.html` -> `kho-acc.html`
- `printing.html`, `custom.html` -> `dich-vu.html`
- `rewards.html` -> `giftcode.html`
- `community.html` -> `tin-tuc.html`

Cloudflare `_redirects` giữ các URL cũ hoạt động.

## Kiểm tra
Các trang và asset chính đã được chạy bằng HTTP local và trả mã 200.

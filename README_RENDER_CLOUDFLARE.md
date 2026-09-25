# Tạp Hóa Delta Force — Cloudflare Pages + Render Flask

## Kiến trúc

- Cloudflare Pages phục vụ `public/`.
- Cloudflare Pages Functions tại `functions/api/[[path]].js` chuyển `/api/*` sang Render.
- `functions/images/[[path]].js` chuyển ảnh upload `/images/*` sang Render.
- Render chạy Flask/Gunicorn từ `app.py`.
- SQLite nằm trong `SHOP_DATA_DIR`. Muốn dữ liệu không mất trên Render cần Persistent Disk.

## 1. GitHub

Chép toàn bộ nội dung gói này vào repository `tap-hoa-delta-force`, sau đó:

```powershell
git add .
git commit -m "add render backend"
git push
```

Cloudflare Pages vẫn giữ cấu hình:

- Production branch: `main`
- Framework preset: `None`
- Build command: `exit 0`
- Build output directory: `public`
- Root directory: để trống

## 2. Render Web Service

Render Dashboard -> New -> Web Service -> chọn repository `tap-hoa-delta-force`.

Thiết lập:

- Language: Python 3
- Branch: main
- Root Directory: để trống
- Build Command: `pip install -r requirements.txt`
- Start Command: `gunicorn app:application --bind 0.0.0.0:$PORT --workers 1 --threads 4 --timeout 120`
- Health Check Path: `/healthz`

Environment variables:

- `SHOP_HTTPS=1`
- `SHOP_ADMIN_PASSWORD=<mật khẩu admin từ 12 ký tự trở lên>`
- `SHOP_SECRET_KEY=<chuỗi bí mật dài, ngẫu nhiên>`

`SHOP_ADMIN_PASSWORD` chỉ được dùng để tạo tài khoản admin nếu database chưa có admin. Đổi mật khẩu trong trang quản trị sau đó không bị ghi đè nếu database vẫn còn.

### Dữ liệu bền vững

Render mặc định dùng filesystem tạm thời. Nếu chạy SQLite lâu dài, gắn Persistent Disk vào Web Service:

- Mount path: `/var/data`
- Environment variable: `SHOP_DATA_DIR=/var/data`

Ảnh upload sẽ tự nằm ở `/var/data/images`.

Nếu không gắn disk, website vẫn chạy để thử nhưng database/ảnh upload có thể mất khi service restart hoặc redeploy.

## 3. Kết nối Cloudflare Pages -> Render

Sau khi Render deploy xong, lấy URL ví dụ:

`https://tap-hoa-delta-force-api.onrender.com`

Cloudflare Dashboard -> Workers & Pages -> `tap-hoa-delta-force` -> Settings -> Variables and Secrets -> Add:

- Variable name: `BACKEND_ORIGIN`
- Value: URL Render, ví dụ `https://tap-hoa-delta-force-api.onrender.com`

Không thêm dấu `/` ở cuối cũng được. Sau khi lưu, redeploy Cloudflare Pages.

## 4. Kiểm tra

- Trang khách: `https://tap-hoa-delta-force.pages.dev/`
- Admin: `https://tap-hoa-delta-force.pages.dev/admin`
- Backend health: `https://<render-url>/healthz`

Admin dùng `/api/*` cùng domain Cloudflare, nên cookie đăng nhập và CSRF vẫn hoạt động qua proxy.

## 5. Cập nhật code

```powershell
git add .
git commit -m "auto version update"
git push
```

GitHub push sẽ kích hoạt cả Cloudflare Pages và Render auto-deploy nếu cả hai đang liên kết branch `main`.

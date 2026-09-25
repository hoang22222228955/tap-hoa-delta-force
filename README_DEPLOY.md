# Tạp Hóa Delta Force — GitHub + Cloudflare Pages

## Cấu trúc
- `public/`: website tĩnh được Cloudflare Pages deploy.
- Không có `admin.html`, Flask, SQLite hoặc dữ liệu khách hàng trong gói public.

## GitHub
Tạo repository trống trên GitHub, ví dụ: `tap-hoa-delta-force`.
Không tạo sẵn README/.gitignore/license nếu muốn dùng lệnh bên dưới nguyên xi.

Trong PowerShell/CMD tại thư mục này:

```bash
git init -b main
git add .
git commit -m "auto version update"
git remote add origin https://github.com/hoang22222228955/tap-hoa-delta-force.git
git push -u origin main
```

Các lần sau:

```bash
git add .
git commit -m "auto version update"
git push
```

## Cloudflare Pages
1. Cloudflare Dashboard -> Workers & Pages -> Create application -> Pages.
2. Import an existing Git repository.
3. Chọn repository `tap-hoa-delta-force`.
4. Production branch: `main`.
5. Build command: `exit 0`.
6. Build output directory: `public`.
7. Save and Deploy.

Mỗi lần push lên nhánh `main`, Cloudflare Pages sẽ tự build/deploy lại.

## Lưu ý về Admin
Bản này là storefront tĩnh. `admin.html` của bản Flask cũ không chạy trên Cloudflare Pages vì nó cần Python + SQLite + API server.
Giữ bản Source Clean riêng để quản trị/local backup. Nếu muốn Admin hoạt động online, backend cần được chuyển sang kiến trúc phù hợp Cloudflare (Workers + D1/R2) hoặc host Flask ở một dịch vụ chạy Python.

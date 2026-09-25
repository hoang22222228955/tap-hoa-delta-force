# V27 — Gallery ảnh acc

Bản này nâng cấp phần **Xem chi tiết** và **Quản trị ảnh sản phẩm** mà không đổi tông giao diện Delta Force hiện tại.

## Đã bổ sung

- 1 **ảnh đại diện** cho mỗi acc/dịch vụ.
- Tối đa **20 ảnh chi tiết** cho mỗi sản phẩm.
- Admin có thể:
  - dán link HTTPS;
  - tải nhiều ảnh chi tiết cùng lúc;
  - đổi thứ tự ảnh bằng nút ↑ / ↓;
  - xóa từng ảnh;
  - xem số lượng `00 / 20` trước khi lưu.
- Backend SQLite tự thêm cột `detail_images` khi deploy bản mới, không cần tạo lại database.
- API `/api/admin/products` kiểm tra tối đa 20 ảnh, loại ảnh trùng và trả `detailImages` cho storefront.
- Popup **Xem chi tiết** mới:
  - ảnh chính dùng `object-fit: contain`, không kéo giãn/cắt méo ảnh;
  - thumbnail ngang;
  - nút ảnh trước/sau;
  - phím ← / →;
  - responsive trên điện thoại;
  - vẫn dùng Chakra Petch/Kanit, nền xanh đen, viền kỹ thuật, xanh tactical và vàng giá của website hiện tại.

## Deploy

Chép đè toàn bộ bản này vào repo đang dùng rồi chạy:

```powershell
git add .
git commit -m "upgrade product detail gallery"
git push
```

Cloudflare Pages và Render sẽ tự deploy từ branch `main` nếu Auto Deploy đang bật.

## Lưu ý Render Free

Ảnh upload từ Admin hiện vẫn được Flask lưu trong filesystem của Render. Gói Free không có persistent disk, nên file upload và SQLite không phải lưu trữ bền vững qua mọi lần restart/redeploy. Khi dùng shop thật, nên chuyển ảnh sang R2/Cloudinary và database sang PostgreSQL hoặc dùng Persistent Disk.

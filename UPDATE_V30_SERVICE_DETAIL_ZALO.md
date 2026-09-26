# V30 — Service detail + Zalo per item

- Ảnh trên thẻ Dịch vụ có thể bấm để mở hồ sơ chi tiết riêng, thiết kế khác popup Kho acc.
- Popup dịch vụ có gallery ảnh đại diện + tối đa 20 ảnh chi tiết, thumbnail, nút trước/sau và phím mũi tên.
- Acc và Dịch vụ có thể đặt số Zalo riêng trong Admin.
- Form Thêm/Sửa acc / dịch vụ để trống số Zalo theo mặc định và có hai gợi ý nhanh: `0769791578`, `0394781498`.
- Nếu để trống số riêng, storefront tự dùng số Zalo chung trong Cài đặt shop.
- Nút hỏi mua/hỏi dịch vụ tự mở đúng số Zalo của mục đang xem.
- PostgreSQL/SQLite tự migrate thêm cột `zalo_phone`, không cần xóa database cũ.

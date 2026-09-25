# V28.1 healthz proxy fix

- Added `/api/healthz` alias in Flask.
- Cloudflare Pages `/api/healthz` now explicitly proxies to Render `/healthz`.
- Fixes `{"error":"Không tìm thấy dữ liệu."}` when testing health through Pages.

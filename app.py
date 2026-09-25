"""Tạp Hóa Delta Force — Flask + SQLite. Run: python app.py (Python 3.11+)."""
from __future__ import annotations

import argparse
import getpass
import io
import json
import os
import re
import secrets
import sqlite3
import threading
import tempfile
import time
import uuid
import webbrowser
import zipfile
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from functools import wraps
from pathlib import Path
from urllib.parse import urlsplit

from flask import Flask, jsonify, request, send_file, send_from_directory, session
from PIL import Image, ImageOps, UnidentifiedImageError
from werkzeug.exceptions import HTTPException
from werkzeug.security import check_password_hash, generate_password_hash

ROOT = Path(__file__).resolve().parent
PUBLIC_ROOT = ROOT / 'public' if (ROOT / 'public').is_dir() else ROOT
SCHEMA = """
CREATE TABLE IF NOT EXISTS admin (id INTEGER PRIMARY KEY CHECK(id=1), password_hash TEXT NOT NULL, version INTEGER NOT NULL DEFAULT 1);
CREATE TABLE IF NOT EXISTS settings (id INTEGER PRIMARY KEY CHECK(id=1), value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS products (id TEXT PRIMARY KEY, name TEXT NOT NULL, category TEXT NOT NULL, price INTEGER NOT NULL CHECK(price>=0), spec TEXT NOT NULL, image TEXT NOT NULL, atlas_index INTEGER, description TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1, detail_images TEXT NOT NULL DEFAULT '[]');
CREATE TABLE IF NOT EXISTS customers (phone TEXT PRIMARY KEY, name TEXT NOT NULL DEFAULT '');
CREATE TABLE IF NOT EXISTS orders (id TEXT PRIMARY KEY, phone TEXT NOT NULL REFERENCES customers(phone), item TEXT NOT NULL, amount INTEGER NOT NULL CHECK(amount>0), status TEXT NOT NULL DEFAULT 'pending', points INTEGER NOT NULL DEFAULT 0, created TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS rewards (id TEXT PRIMARY KEY, name TEXT NOT NULL, cost INTEGER NOT NULL CHECK(cost>0), active INTEGER NOT NULL DEFAULT 1);
CREATE TABLE IF NOT EXISTS redemptions (id TEXT PRIMARY KEY, phone TEXT NOT NULL REFERENCES customers(phone), reward_id TEXT NOT NULL REFERENCES rewards(id), reward_name TEXT NOT NULL, cost INTEGER NOT NULL CHECK(cost>0), status TEXT NOT NULL DEFAULT 'done', created TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE INDEX IF NOT EXISTS orders_phone ON orders(phone,status);
CREATE INDEX IF NOT EXISTS redemptions_phone ON redemptions(phone,status);
CREATE TABLE IF NOT EXISTS login_attempts (address TEXT NOT NULL, attempted REAL NOT NULL);
"""


class APIError(Exception):
    def __init__(self, message, code=400):
        self.message, self.code = message, code


def clean_text(value, name, maxlen=150, required=True):
    if not isinstance(value, str):
        raise APIError(f'{name} không hợp lệ.')
    value = value.strip()
    if (required and not value) or len(value) > maxlen:
        raise APIError(f'{name} cần từ {1 if required else 0} đến {maxlen} ký tự.')
    return value


def integer(value, name, minimum=0, maximum=1_000_000_000):
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        raise APIError(f'{name} phải là số nguyên.')
    if isinstance(value, str) and not re.fullmatch(r'\d+', value):
        raise APIError(f'{name} phải là số nguyên.')
    result = int(value)
    if not minimum <= result <= maximum:
        raise APIError(f'{name} cần nằm trong khoảng {minimum:,}–{maximum:,}.')
    return result


def phone_number(value, allow_empty=False):
    if not isinstance(value, str):
        raise APIError('Số điện thoại không hợp lệ.')
    value = re.sub(r'[\s+().-]', '', value)
    if not value and allow_empty:
        return ''
    if value.startswith('84'):
        value = '0' + value[2:]
    if not re.fullmatch(r'0[35789]\d{8}', value):
        raise APIError('Nhập số di động Việt Nam gồm 10 chữ số (hoặc +84).')
    return value


def request_id(value):
    try:
        return str(uuid.UUID(str(value)))
    except (ValueError, TypeError, AttributeError):
        raise APIError('Mã yêu cầu không hợp lệ. Vui lòng tải lại trang.')


# Additive migrations: old orders and spent points retain their original meaning.
UPGRADE_COLUMNS = {
    'products': {'detail_images': "TEXT NOT NULL DEFAULT '[]'"},
    'rewards': {'kind': "TEXT NOT NULL DEFAULT 'model'", 'description': "TEXT NOT NULL DEFAULT ''",
        'terms': "TEXT NOT NULL DEFAULT ''", 'product_id': "TEXT NOT NULL DEFAULT ''",
        'stock': 'INTEGER NOT NULL DEFAULT -1', 'per_customer_limit': 'INTEGER NOT NULL DEFAULT 0',
        'valid_days': 'INTEGER NOT NULL DEFAULT 0', 'value_amount': 'INTEGER NOT NULL DEFAULT 0',
        'min_order': 'INTEGER NOT NULL DEFAULT 0', 'start_date': "TEXT NOT NULL DEFAULT ''", 'end_date': "TEXT NOT NULL DEFAULT ''"},
    'redemptions': {'snapshot': "TEXT NOT NULL DEFAULT '{}'", 'code': 'TEXT',
        'expires_at': "TEXT NOT NULL DEFAULT ''", 'stock_reserved': 'INTEGER NOT NULL DEFAULT 0', 'order_id': 'TEXT'},
    'orders': {'discount': 'INTEGER NOT NULL DEFAULT 0', 'redemption_id': 'TEXT', 'voucher_code': "TEXT NOT NULL DEFAULT ''",
        'tech': "TEXT NOT NULL DEFAULT ''", 'production_stage': "TEXT NOT NULL DEFAULT 'new'",
        'due_date': "TEXT NOT NULL DEFAULT ''", 'internal_note': "TEXT NOT NULL DEFAULT ''"}
}
REWARD_KINDS = {'model', 'voucher', 'accessory', 'printing', 'shipping'}
PRODUCTION_STAGES = {
    'new': 'Mới tạo', 'brief_received': 'Đã đủ thông tin', 'approved': 'Đã xác nhận yêu cầu',
    'printing_resin': 'Đang xử lý dịch vụ', 'printing_fdm': 'Đang kiểm tra / bàn giao',
    'finishing': 'Đang hoàn thiện', 'ready': 'Sẵn sàng chốt', 'shipped': 'Đã bàn giao'
}


def migrate_v5(db):
    for table, columns in UPGRADE_COLUMNS.items():
        existing = {r[1] for r in db.execute('PRAGMA table_info(' + table + ')')}
        for name, spec in columns.items():
            if name not in existing:
                db.execute(f'ALTER TABLE {table} ADD COLUMN {name} {spec}')
    db.execute('CREATE UNIQUE INDEX IF NOT EXISTS redemption_code ON redemptions(code) WHERE code IS NOT NULL')
    db.execute("CREATE TABLE IF NOT EXISTS point_adjustments(id TEXT PRIMARY KEY, phone TEXT NOT NULL REFERENCES customers(phone), delta INTEGER NOT NULL CHECK(delta<>0), reason TEXT NOT NULL, created TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)")
    db.execute('PRAGMA user_version=5')


def migrate_delta_storefront(db):
    """Upgrade old MORI/early merged data folders to the Delta storefront once.

    Admin/customer/order data is kept. Only the legacy MORI catalog/settings are
    replaced when they are clearly the old 3D-printing defaults. Early Delta
    installs keep user edits, while bundled placeholder atlas images are upgraded
    to the original shop image URLs.
    """
    seed = json.loads((ROOT / 'catalog.json').read_text(encoding='utf-8'))
    row = db.execute('SELECT value FROM settings WHERE id=1').fetchone()
    if not row:
        return
    try:
        raw = json.loads(row[0])
    except (TypeError, json.JSONDecodeError):
        raw = {}
    products = list(db.execute('SELECT id,category,image,atlas_index FROM products'))
    ids = {r['id'] for r in products}
    categories = {r['category'] for r in products}
    legacy_ids = {'PRO-01','PRO-02','PRO-03','PRO-04','HOME-01','HOME-02','HOME-03','HOME-04','PROP-01','GAME-02'}
    legacy_categories = {'anime','game','chibi','household','prop'}
    brand = f"{raw.get('name','')} {raw.get('fullName','')}".lower()
    legacy = ('mori' in brand) or bool(ids & legacy_ids) or bool(categories & legacy_categories)

    if legacy:
        fresh = dict(seed['settings'])
        # Keep the shop's already configured contact/reward ratio when sensible.
        if isinstance(raw.get('zalo'), str) and raw.get('zalo').strip():
            fresh['zalo'] = raw['zalo'].strip()
        if isinstance(raw.get('vndPerPoint'), int) and raw['vndPerPoint'] > 0:
            fresh['vndPerPoint'] = raw['vndPerPoint']
        fresh['storefrontVersion'] = 3
        db.execute('UPDATE settings SET value=? WHERE id=1', (json.dumps(fresh, ensure_ascii=False),))
        db.execute('DELETE FROM products')
        for item in seed['products']:
            db.execute('INSERT INTO products(id,name,category,price,spec,image,atlas_index,description,active) VALUES(?,?,?,?,?,?,?,?,1)',
                       (item['id'], item['name'], item['category'], item['price'], item['spec'], item['image'], item.get('atlasIndex'), item['description']))
        # Retire the bundled MORI reward catalog too. Referenced historical
        # rewards are retained but hidden so old customer history stays valid.
        legacy_reward_ids = ('R100','R200','R350','R060','R180','R090','R040')
        for rid in legacy_reward_ids:
            referenced = db.execute('SELECT 1 FROM redemptions WHERE reward_id=? LIMIT 1', (rid,)).fetchone()
            if referenced:
                db.execute('UPDATE rewards SET active=0 WHERE id=?', (rid,))
            else:
                db.execute('DELETE FROM rewards WHERE id=?', (rid,))
        for reward in seed.get('rewards', []):
            db.execute('INSERT INTO rewards(id,name,cost,active) VALUES(?,?,?,1) '
                       'ON CONFLICT(id) DO UPDATE SET name=excluded.name,cost=excluded.cost,active=1',
                       (reward['id'], reward['name'], reward['cost']))
            for key in UPGRADE_COLUMNS['rewards']:
                if key in reward:
                    db.execute(f'UPDATE rewards SET {key}=? WHERE id=?', (reward[key], reward['id']))
        return

    version = int(raw.get('storefrontVersion') or 0) if str(raw.get('storefrontVersion') or 0).isdigit() else 0
    if version < 3:
        defaults = {item['id']: item for item in seed['products']}
        for item in products:
            default = defaults.get(item['id'])
            if not default:
                continue
            # Only replace the bundled MORI atlas placeholders. Uploaded/custom
            # images are left untouched.
            if item['image'] in ('images/models.png', 'images/prints.png') and item['atlas_index'] is not None:
                db.execute('UPDATE products SET image=?, atlas_index=NULL WHERE id=?',
                           (default['image'], item['id']))
        raw['storefrontVersion'] = 3
        # Early merged installs may have correct Delta categories already; retain
        # all user settings and only add the migration marker.
        db.execute('UPDATE settings SET value=? WHERE id=1', (json.dumps(raw, ensure_ascii=False),))


def utc_stamp():
    return datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')


def reward_available(r):
    today = utc_stamp()[:10]
    return bool(r['active'] and r['stock'] != 0 and
                (not r['start_date'] or r['start_date'] <= today) and
                (not r['end_date'] or r['end_date'] >= today))


def date_value(value, label):
    value = clean_text(value, label, 10, False)
    if value:
        try:
            if datetime.strptime(value, '%Y-%m-%d').strftime('%Y-%m-%d') != value:
                raise ValueError()
        except ValueError:
            raise APIError(label + ' cần có dạng YYYY-MM-DD.')
    return value


def create_app(data_dir=None, images_dir=None, testing=False):
    app = Flask(__name__, static_folder=None)
    configured_data = data_dir or os.environ.get('SHOP_DATA_DIR')
    storage = Path(configured_data) if configured_data else ROOT / 'data'
    configured_images = images_dir or os.environ.get('SHOP_IMAGES_DIR')
    pictures = Path(configured_images) if configured_images else (storage / 'images' if configured_data else ROOT / 'images')
    storage.mkdir(parents=True, exist_ok=True)
    pictures.mkdir(parents=True, exist_ok=True)
    dbpath = storage / 'shop.sqlite3'
    keypath = storage / 'session.key'
    configured_secret = os.environ.get('SHOP_SECRET_KEY', '').strip()
    if configured_secret:
        secret_key = configured_secret
    else:
        if not keypath.exists():
            try:
                with keypath.open('x') as f:
                    f.write(secrets.token_hex(48))
                keypath.chmod(0o600)
            except FileExistsError:
                pass
        secret_key = keypath.read_text().strip()
    app.config.update(SECRET_KEY=secret_key, TESTING=testing,
                      SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE='Lax',
                      SESSION_COOKIE_SECURE=os.environ.get('SHOP_HTTPS') == '1',
                      PERMANENT_SESSION_LIFETIME=timedelta(hours=8), MAX_CONTENT_LENGTH=8*1024*1024)
    app.config['DB_PATH'], app.config['IMAGES_PATH'] = dbpath, pictures

    @contextmanager
    def database(write=False):
        db = sqlite3.connect(dbpath, timeout=15)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        try:
            if write:
                db.execute('BEGIN IMMEDIATE')
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    app.database = database
    with database() as db:
        db.execute('PRAGMA journal_mode=WAL')
        db.executescript(SCHEMA)
    with database(True) as db:
        migrate_v5(db)
        if not db.execute('SELECT 1 FROM settings').fetchone():
            seed = json.loads((ROOT / 'catalog.json').read_text(encoding='utf-8'))
            db.execute('INSERT INTO settings VALUES(1,?)', (json.dumps(seed['settings'], ensure_ascii=False),))
            for p in seed['products']:
                db.execute('INSERT INTO products(id,name,category,price,spec,image,atlas_index,description,active) VALUES(?,?,?,?,?,?,?,?,1)', (p['id'],p['name'],p['category'],p['price'],p['spec'],p['image'],p.get('atlasIndex'),p['description']))
            for r in seed['rewards']:
                db.execute('INSERT INTO rewards(id,name,cost) VALUES(?,?,?)',(r['id'],r['name'],r['cost']))
                for key in UPGRADE_COLUMNS['rewards']:
                    if key in r:
                        db.execute(f'UPDATE rewards SET {key}=? WHERE id=?',(r[key],r['id']))
        migrate_delta_storefront(db)
        # 4.2 migration: the previous bundled default was 4.2 seconds.
        # Move that legacy default to 2.5 seconds so an existing data folder
        # does not keep the old slideshow speed after upgrading.
        row = db.execute('SELECT value FROM settings WHERE id=1').fetchone()
        if row:
            current = json.loads(row[0])
            if current.get('heroInterval') == 4200:
                current['heroInterval'] = 2500
                current['heroAutoplay'] = True
                db.execute('UPDATE settings SET value=? WHERE id=1',
                           (json.dumps(current, ensure_ascii=False),))

    def settings(db):
        # Merge stored settings with the current defaults so older backups keep working
        # after new storefront/admin options are introduced.
        raw = json.loads(db.execute('SELECT value FROM settings WHERE id=1').fetchone()[0])
        defaults = json.loads((ROOT / 'catalog.json').read_text(encoding='utf-8'))['settings']
        value = {**defaults, **raw}
        if 'giftHeroType' not in raw:
            value['giftHeroType'] = 'image' if raw.get('giftHeroImage') else 'video'
        value['groups'] = {**defaults.get('groups', {}), **(raw.get('groups') or {})}
        if not isinstance(value.get('categories'), list) or not value['categories']:
            value['categories'] = defaults['categories']
        if not isinstance(value.get('communityBoxes'), list):
            value['communityBoxes'] = defaults['communityBoxes']
        # Older installs kept the sample announcement inside SQLite. Update
        # only that unchanged sample when the bundle size or price changes.
        if isinstance(value.get('deltaNews'), list):
            news = []
            for item in value['deltaNews']:
                summary = item.get('summary', '') if isinstance(item, dict) else ''
                sample = summary == 'Nhận nhập tối đa 300 code, giá 20.000đ mỗi code và xử lý theo lượt.'
                sample = sample or (isinstance(summary, str) and re.fullmatch(r'Nhận nhập gói \d+ code với giá trọn gói [\d.]+ ₫\.', summary))
                if isinstance(item, dict) and item.get('id') == 'NEWS-003' and sample:
                    item = dict(item)
                    total = value.get('giftTotal', 300)
                    price = value.get('giftPrice', 20000)
                    if isinstance(total, int) and isinstance(price, int):
                        item['summary'] = f'Nhận nhập gói {total} code với giá trọn gói {price:,} ₫.'.replace(',', '.')
                        if re.fullmatch(r'NHẬN NHẬP \d+ GIFTCODE DELTA FORCE', str(item.get('title', ''))):
                            item['title'] = f'NHẬN NHẬP {total} GIFTCODE DELTA FORCE'
                news.append(item)
            value['deltaNews'] = news
        return value

    def product_dict(row):
        p = dict(row)
        p['atlasIndex'] = p.pop('atlas_index')
        raw = p.pop('detail_images', '[]')
        try:
            detail = json.loads(raw) if isinstance(raw, str) else raw
        except (TypeError, json.JSONDecodeError):
            detail = []
        p['detailImages'] = [str(item).strip() for item in detail if isinstance(item, str) and str(item).strip()][:20] if isinstance(detail, list) else []
        return p

    def store_data(db):
        return {'settings': settings(db), 'products': [product_dict(p) for p in db.execute('SELECT * FROM products WHERE active=1 ORDER BY rowid')],
                'rewards': [dict(r) | {'available':reward_available(r)} for r in db.execute('SELECT * FROM rewards WHERE active=1 ORDER BY cost')]}

    def balance(db, phone):
        earned = db.execute("SELECT COALESCE(SUM(points),0) FROM orders WHERE phone=? AND status='completed'", (phone,)).fetchone()[0]
        spent = db.execute("SELECT COALESCE(SUM(cost),0) FROM redemptions WHERE phone=? AND status<>'cancelled'", (phone,)).fetchone()[0]
        adjusted = db.execute('SELECT COALESCE(SUM(delta),0) FROM point_adjustments WHERE phone=?',(phone,)).fetchone()[0]
        return earned + adjusted - spent

    def is_admin():
        if not session.get('admin'):
            return False
        with database() as db:
            row = db.execute('SELECT version FROM admin WHERE id=1').fetchone()
        return bool(row and session.get('version') == row['version'])

    def body():
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            raise APIError('Dữ liệu gửi lên phải là JSON hợp lệ.')
        return data

    def customer(db, phone, name=''):
        db.execute('INSERT INTO customers(phone,name) VALUES(?,?) ON CONFLICT(phone) DO UPDATE SET name=CASE WHEN excluded.name<>\'\' THEN excluded.name ELSE customers.name END', (phone,name))

    @app.before_request
    def guard():
        if request.path.startswith('/api/') and request.method in ('POST','PUT','PATCH','DELETE'):
            expected, actual = session.get('csrf'), request.headers.get('X-CSRF-Token','')
            if not expected or not secrets.compare_digest(expected,actual):
                raise APIError('Phiên bảo vệ đã hết hạn. Vui lòng tải lại trang.',403)
        if request.path.startswith('/api/admin/') and not is_admin():
            raise APIError('Vui lòng đăng nhập quản trị.',401)

    @app.after_request
    def headers(response):
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['Referrer-Policy'] = 'same-origin'
        response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src 'self' data: https://fonts.gstatic.com; img-src 'self' data: blob: https:; frame-src https://www.tiktok.com; connect-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'; form-action 'self'"
        if request.path.startswith(('/api/','/admin','/catalog.js')):
            response.headers['Cache-Control'] = 'no-store'
        return response

    @app.errorhandler(APIError)
    def api_error(err):
        return jsonify(error=err.message), err.code

    @app.errorhandler(HTTPException)
    def http_error(err):
        if request.path.startswith('/api/'):
            message = 'Ảnh quá lớn. Giới hạn tải lên là 8 MB.' if err.code==413 else ('Không tìm thấy dữ liệu.' if err.code==404 else 'Yêu cầu không hợp lệ.')
            return jsonify(error=message),err.code
        return err

    @app.errorhandler(sqlite3.Error)
    def db_error(err):
        app.logger.exception('Database error')
        return jsonify(error='Chưa lưu được dữ liệu. Vui lòng thử lại, giữ nguyên biểu mẫu để tránh tạo đơn trùng.'),503

    def html_page(filename):
        response = send_from_directory(PUBLIC_ROOT, filename)
        response.headers['Cache-Control'] = 'no-store, max-age=0'
        return response

    @app.get('/')
    @app.get('/index.html')
    def index():
        return html_page('index.html')

    @app.get('/printing.html')
    @app.get('/products.html')
    @app.get('/custom.html')
    @app.get('/rewards.html')
    @app.get('/community.html')
    @app.get('/market.html')
    @app.get('/kho-acc.html')
    @app.get('/dich-vu.html')
    @app.get('/giftcode.html')
    @app.get('/tin-tuc.html')
    def public_pages():
        page=request.path.lstrip('/')
        legacy_map={
            'printing.html':'dich-vu.html',
            'products.html':'kho-acc.html',
            'custom.html':'dich-vu.html',
            'rewards.html':'giftcode.html',
            'community.html':'tin-tuc.html',
            'market.html':'kho-acc.html',
        }
        allowed={'kho-acc.html','dich-vu.html','giftcode.html','tin-tuc.html'} | set(legacy_map)
        if page not in allowed:
            raise APIError('Không tìm thấy trang.',404)
        return html_page(legacy_map.get(page,page))

    @app.get('/admin')
    @app.get('/admin.html')
    def admin_page():
        return send_from_directory(PUBLIC_ROOT,'admin.html')

    @app.get('/favicon.svg')
    def favicon():
        response = send_from_directory(PUBLIC_ROOT, 'favicon.svg')
        response.headers['Cache-Control'] = 'no-store'
        return response

    @app.get('/images/<filename>')
    def images(filename):
        if not re.fullmatch(r'(?:(?:models|prints)\.png|[a-f0-9]{32}\.webp)', filename):
            raise APIError('Không tìm thấy ảnh.',404)
        return send_from_directory(pictures,filename,max_age=86400)

    @app.get('/assets/<path:filename>')
    def assets(filename):
        return send_from_directory(PUBLIC_ROOT/'assets', filename, max_age=3600)

    @app.get('/catalog.js')
    @app.get('/api/catalog.js')
    def bootstrap():
        with database() as db:
            data=store_data(db)
        return app.response_class('window.DELTA_CATALOG = '+json.dumps(data,ensure_ascii=False)+';\n',mimetype='text/javascript')

    @app.get('/healthz')
    def healthz():
        return jsonify(ok=True)

    @app.get('/api/session')
    def current_session():
        if 'csrf' not in session:
            session['csrf']=secrets.token_hex(32)
        return jsonify(csrf=session['csrf'],loggedIn=is_admin())

    @app.post('/api/login')
    def login():
        password=body().get('password','')
        if not isinstance(password,str) or len(password)>300:
            raise APIError('Mật khẩu không hợp lệ.')
        address=(request.headers.get('CF-Connecting-IP') or request.headers.get('X-Forwarded-For','').split(',')[0].strip() or request.remote_addr or 'local')
        now=time.time()
        with database(True) as db:
            db.execute('DELETE FROM login_attempts WHERE attempted<?',(now-900,))
            if db.execute('SELECT COUNT(*) FROM login_attempts WHERE address=?',(address,)).fetchone()[0]>=6:
                raise APIError('Đăng nhập sai quá nhiều lần. Hãy thử lại sau 15 phút.',429)
            row=db.execute('SELECT * FROM admin WHERE id=1').fetchone()
            valid=bool(row and check_password_hash(row['password_hash'],password))
            if not valid:
                db.execute('INSERT INTO login_attempts VALUES(?,?)',(address,now))
            else:
                db.execute('DELETE FROM login_attempts WHERE address=?',(address,))
        if not valid:
            raise APIError('Mật khẩu chưa đúng hoặc quản trị chưa được thiết lập.',401)
        session.clear()
        session.update(admin=True,version=row['version'],csrf=secrets.token_hex(32))
        session.permanent=True
        return jsonify(ok=True,csrf=session['csrf'])

    @app.post('/api/logout')
    def logout():
        session.clear()
        return jsonify(ok=True)

    @app.get('/api/admin/data')
    def admin_data():
        with database() as db:
            data=store_data(db)
            data['products']=[product_dict(p) for p in db.execute('SELECT * FROM products ORDER BY rowid DESC')]
            data['rewards']=[dict(r) | {'available':reward_available(r)} for r in db.execute('SELECT * FROM rewards ORDER BY cost')]
            data['customers']=[dict(r)|{'balance':balance(db,r['phone'])} for r in db.execute('SELECT * FROM customers ORDER BY rowid DESC')]
            data['orders']=[dict(r) for r in db.execute('SELECT o.*,c.name FROM orders o JOIN customers c ON c.phone=o.phone ORDER BY o.rowid DESC LIMIT 200')]
            data['redemptions']=[dict(r) for r in db.execute('SELECT * FROM redemptions ORDER BY rowid DESC LIMIT 200')]
            production={stage:db.execute('SELECT COUNT(*) FROM orders WHERE production_stage=? AND status NOT IN (\'cancelled\',\'refunded\')',(stage,)).fetchone()[0] for stage in PRODUCTION_STAGES}
            data['stats']={
                'revenue':db.execute("SELECT COALESCE(SUM(amount-discount),0) FROM orders WHERE status='completed'").fetchone()[0],
                'completed':db.execute("SELECT COUNT(*) FROM orders WHERE status='completed'").fetchone()[0],
                'pending':db.execute("SELECT COUNT(*) FROM orders WHERE status='pending'").fetchone()[0],
                'customers':len(data['customers']), 'production':production}
        return jsonify(data)

    def validated_gift_image(value):
        image=clean_text(value,'Ảnh minh họa giftcode',1000,False)
        if image and not (re.fullmatch(r'https://[^\s]+',image,re.I) or re.fullmatch(r'images/[a-f0-9]{32}\.webp',image)):
            raise APIError('Ảnh giftcode phải là link HTTPS hoặc ảnh được tải lên từ trang quản trị.')
        if re.fullmatch(r'images/[a-f0-9]{32}\.webp',image) and not (pictures/Path(image).name).is_file():
            raise APIError('Ảnh giftcode tải lên chưa tồn tại. Hãy tải lại ảnh.')
        return image

    def validated_gift_video(value):
        link=clean_text(value,'Link video TikTok',1000,False)
        if not link:
            return ''
        try:
            parsed=urlsplit(link)
            match=re.fullmatch(r'/@([a-zA-Z0-9._]{2,24})/video/([0-9]{10,22})/?',parsed.path)
            valid=(parsed.scheme=='https' and parsed.hostname in ('www.tiktok.com','tiktok.com')
                   and parsed.port is None and parsed.username is None and parsed.password is None and match)
        except ValueError:
            valid=False
        if not valid:
            raise APIError('Dán link video TikTok dạng https://www.tiktok.com/@ten/video/ma-video.')
        return f'https://www.tiktok.com/@{match.group(1)}/video/{match.group(2)}'

    @app.post('/api/admin/gift-image')
    def update_gift_image():
        image=validated_gift_image(body().get('image',''))
        with database(True) as db:
            current=json.loads(db.execute('SELECT value FROM settings WHERE id=1').fetchone()[0])
            current['giftHeroImage']=image
            current['giftHeroType']='image'
            db.execute('UPDATE settings SET value=? WHERE id=1',(json.dumps(current,ensure_ascii=False),))
        return jsonify(ok=True,image=image)

    @app.post('/api/admin/gift-media')
    def update_gift_media():
        d=body()
        media_type=d.get('type')
        if media_type not in ('image','video'):
            raise APIError('Chọn Ảnh hoặc Video TikTok cho khung Giftcode.')
        image=validated_gift_image(d.get('image',''))
        video=validated_gift_video(d.get('video',''))
        if media_type=='video' and not video:
            raise APIError('Dán link video TikTok trước khi lưu.')
        with database(True) as db:
            current=json.loads(db.execute('SELECT value FROM settings WHERE id=1').fetchone()[0])
            current.update(giftHeroType=media_type,giftHeroImage=image,giftHeroVideo=video)
            db.execute('UPDATE settings SET value=? WHERE id=1',(json.dumps(current,ensure_ascii=False),))
        return jsonify(ok=True,type=media_type,image=image,video=video)

    @app.post('/api/admin/settings')
    def update_settings():
        d=body()
        if not isinstance(d.get('demo'),bool):
            raise APIError('Trạng thái dữ liệu mẫu không hợp lệ.')

        categories=d.get('categories')
        if not isinstance(categories,list) or not 1<=len(categories)<=12:
            raise APIError('Danh mục cần có từ 1 đến 12 mục.')
        checked_categories=[]
        seen=set()
        for item in categories:
            if not isinstance(item,dict):
                raise APIError('Dữ liệu danh mục không hợp lệ.')
            cid=clean_text(item.get('id'),'Mã danh mục',32).lower()
            if not re.fullmatch(r'[a-z0-9][a-z0-9_-]{1,31}',cid):
                raise APIError('Mã danh mục chỉ dùng chữ thường, số, gạch ngang hoặc gạch dưới.')
            if cid in seen:
                raise APIError('Mã danh mục đang bị trùng.')
            seen.add(cid)
            checked_categories.append({'id':cid,'name':clean_text(item.get('name'),'Tên danh mục',50)})

        groups=d.get('groups') if isinstance(d.get('groups'),dict) else {}
        boxes=d.get('communityBoxes')
        if not isinstance(boxes,list) or len(boxes)>8:
            raise APIError('Box Zalo cần là danh sách tối đa 8 box.')
        checked_boxes=[]
        checked_groups={}
        box_ids=set()
        for i,item in enumerate(boxes):
            if not isinstance(item,dict):
                raise APIError('Dữ liệu box Zalo không hợp lệ.')
            bid=clean_text(item.get('id') or f'box{i+1}','Mã box',32).lower()
            if not re.fullmatch(r'[a-z0-9][a-z0-9_-]{1,31}',bid) or bid in box_ids:
                raise APIError('Mã box Zalo không hợp lệ hoặc đang bị trùng.')
            box_ids.add(bid)
            title=clean_text(item.get('title'),'Tên box Zalo',80)
            description=clean_text(item.get('description',''),'Mô tả box Zalo',220,False)
            # Keep compatibility with older clients that edit the legacy groups object.
            candidate=groups.get(bid,item.get('url',''))
            url=clean_text(candidate,'Liên kết Zalo',220,False)
            if url and not re.fullmatch(r'https://zalo\.me/(?:g/)?[a-zA-Z0-9_-]+',url):
                raise APIError('Link Zalo cần bắt đầu bằng https://zalo.me/ hoặc https://zalo.me/g/.')
            checked_boxes.append({'id':bid,'title':title,'description':description,'url':url})
            checked_groups[bid]=url

        facebook=clean_text(d.get('facebook',''),'Link Facebook',500,False)
        tiktok=clean_text(d.get('tiktok',''),'Link TikTok',500,False)
        for link,label,hosts in ((facebook,'Facebook',('facebook.com','fb.com')), (tiktok,'TikTok',('tiktok.com',))):
            if not link:
                continue
            try:
                parsed=urlsplit(link)
                host=(parsed.hostname or '').lower()
                valid=(parsed.scheme=='https' and parsed.username is None and parsed.password is None and parsed.port is None
                       and any(host==h or host.endswith('.'+h) for h in hosts))
            except ValueError:
                valid=False
            if not valid:
                raise APIError(f'Link {label} cần là đường dẫn HTTPS hợp lệ của {label}.')

        value={'name':clean_text(d.get('name'),'Tên thương hiệu',24),
               'fullName':clean_text(d.get('fullName'),'Tên shop',80),
               'zalo':phone_number(d.get('zalo',''),True),
               'facebook':facebook,
               'tiktok':tiktok,
               'groups':checked_groups,
               'categories':checked_categories,
               'communityBoxes':checked_boxes,
               'vndPerPoint':integer(d.get('vndPerPoint'),'Giá trị mỗi điểm',1),
               'demo':d['demo'],
               'heroInterval':integer(d.get('heroInterval',2500),'Thời gian chuyển ảnh',2500,10000),
               'heroAutoplay':d.get('heroAutoplay',True),
               'giftTotal':integer(d.get('giftTotal',300),'Số giftcode đang nhận',0,1000000),
               'giftPrice':integer(d.get('giftPrice',20000),'Giá trọn gói giftcode',0,1000000000),
               'giftNote':clean_text(d.get('giftNote',''),'Ghi chú giftcode',220,False)}
        gift_image=None
        if 'giftHeroImage' in d:
            gift_image=validated_gift_image(d['giftHeroImage'])
        if not isinstance(value['heroAutoplay'],bool):
            raise APIError('Trạng thái tự chuyển ảnh không hợp lệ.')
        with database(True) as db:
            # Market listings live in settings so the public storefront can be
            # exported without a second database table. Preserve them when an
            # older Admin client saves general settings.
            current_settings=settings(db)
            value['giftHeroImage']=gift_image if gift_image is not None else current_settings.get('giftHeroImage','')
            value['giftHeroType']=current_settings.get('giftHeroType','video')
            value['giftHeroVideo']=current_settings.get('giftHeroVideo','')
            value['marketItems']=current_settings.get('marketItems',[])
            value['deltaNews']=current_settings.get('deltaNews',[])
            used={r[0] for r in db.execute('SELECT DISTINCT category FROM products')}
            missing=used-set(seen)
            if missing:
                names=', '.join(sorted(missing))
                raise APIError(f'Không thể xóa danh mục đang được sản phẩm sử dụng: {names}. Hãy đổi danh mục sản phẩm trước.')
            db.execute('UPDATE settings SET value=? WHERE id=1',(json.dumps(value,ensure_ascii=False),))
        return jsonify(ok=True)

    def validated_product_image(value, label='Ảnh sản phẩm'):
        image=clean_text(value,label,1000)
        if re.fullmatch(r'https://[^\s]+', image, flags=re.I):
            return image
        if re.fullmatch(r'images/[a-f0-9]{32}\.webp', image):
            if not (pictures/Path(image).name).is_file():
                raise APIError(f'{label} tải lên chưa tồn tại. Hãy tải lại ảnh.')
            return image
        raise APIError(f'{label} phải là link HTTPS hoặc ảnh được tải lên từ trang quản trị.')

    @app.post('/api/admin/products')
    def save_product():
        d=body()
        pid=clean_text(d.get('id'),'Mã sản phẩm',40)
        if not re.fullmatch(r'[a-zA-Z0-9_-]+',pid):
            raise APIError('Mã sản phẩm chỉ dùng chữ, số, dấu gạch ngang hoặc gạch dưới.')
        name=clean_text(d.get('name'),'Tên sản phẩm',120)
        category=clean_text(d.get('category'),'Danh mục',32).lower()
        price=integer(d.get('price'),'Giá bán')
        spec=clean_text(d.get('spec',''),'Thông số',150,False)
        description=clean_text(d.get('description',''),'Mô tả',2000,False)
        atlas=None
        image=validated_product_image(d.get('image',''),'Ảnh đại diện')
        detail_input=d.get('detailImages',[])
        if not isinstance(detail_input,list):
            raise APIError('Danh sách ảnh chi tiết không hợp lệ.')
        if len(detail_input)>20:
            raise APIError('Mỗi acc chỉ được tối đa 20 ảnh chi tiết.')
        detail_images=[]
        seen={image}
        for index,item in enumerate(detail_input,1):
            detail=validated_product_image(item,f'Ảnh chi tiết #{index}')
            if detail not in seen:
                seen.add(detail)
                detail_images.append(detail)
        active=integer(d.get('active',1),'Trạng thái',0,1)
        with database(True) as db:
            allowed={c['id'] for c in settings(db).get('categories',[]) if isinstance(c,dict) and c.get('id')}
            if category not in allowed:
                raise APIError('Danh mục không hợp lệ hoặc đã bị xóa.')
            db.execute('INSERT INTO products(id,name,category,price,spec,image,atlas_index,description,active,detail_images) VALUES(?,?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET name=excluded.name,category=excluded.category,price=excluded.price,spec=excluded.spec,image=excluded.image,atlas_index=excluded.atlas_index,description=excluded.description,active=excluded.active,detail_images=excluded.detail_images',
                       (pid,name,category,price,spec,image,atlas,description,active,json.dumps(detail_images,ensure_ascii=False)))
        return jsonify(ok=True)

    @app.delete('/api/admin/products/<pid>')
    def delete_product(pid):
        pid=clean_text(pid,'Mã sản phẩm',40)
        if not re.fullmatch(r'[a-zA-Z0-9_-]+',pid):
            raise APIError('Mã sản phẩm không hợp lệ.')
        with database(True) as db:
            exists=db.execute('SELECT 1 FROM products WHERE id=?',(pid,)).fetchone()
            if not exists:
                raise APIError('Không tìm thấy acc / dịch vụ cần xóa.',404)
            # Quà/voucher cũ có thể từng liên kết tới mặt hàng này. Bỏ liên kết
            # thay vì xóa lịch sử đổi quà hoặc đơn hàng của shop.
            db.execute("UPDATE rewards SET product_id='' WHERE product_id=?",(pid,))
            db.execute('DELETE FROM products WHERE id=?',(pid,))
        return jsonify(ok=True,id=pid)

    @app.post('/api/admin/upload')
    def upload():
        incoming=request.files.get('image')
        if not incoming:
            raise APIError('Chọn một ảnh PNG, JPEG hoặc WebP.')
        Image.MAX_IMAGE_PIXELS=16_000_000
        try:
            image=Image.open(incoming.stream)
            if image.format not in ('PNG','JPEG','WEBP') or image.width*image.height>16_000_000:
                raise APIError('Ảnh cần là PNG, JPEG hoặc WebP, tối đa 16 megapixel.')
            image.load()
            image=ImageOps.exif_transpose(image).convert('RGBA')
            image.thumbnail((1600,1600))
            filename=uuid.uuid4().hex+'.webp'
            image.save(pictures/filename,'WEBP',quality=90)
        except (UnidentifiedImageError,OSError,Image.DecompressionBombError,ValueError):
            raise APIError('Không đọc được ảnh. Hãy chọn tệp PNG, JPEG hoặc WebP hợp lệ.')
        return jsonify(image='images/'+filename,atlasIndex=None)

    @app.post('/api/admin/orders')
    def create_order():
        d=body()
        oid=request_id(d.get('id'))
        phone=phone_number(d.get('phone'))
        name=clean_text(d.get('name',''),'Tên khách',100,False)
        item=clean_text(d.get('item'),'Nội dung đơn',300)
        amount=integer(d.get('amount'),'Giá trị đơn',1)
        code=clean_text(d.get('voucherCode',''),'Mã voucher',32,False).upper()
        tech=clean_text(d.get('tech',''),'Công nghệ',20,False)
        if tech not in ('','ACC','SERVICE'):
            raise APIError('Loại xử lý chỉ có thể là ACC hoặc SERVICE.')
        due_date=date_value(d.get('dueDate',''),'Ngày dự kiến')
        internal_note=clean_text(d.get('internalNote',''),'Ghi chú nội bộ',1000,False)
        with database(True) as db:
            old=db.execute('SELECT * FROM orders WHERE id=?',(oid,)).fetchone()
            if old:
                if (old['phone'],old['item'],old['amount'],old['voucher_code'],old['tech'],old['due_date'],old['internal_note'])!=(phone,item,amount,code,tech,due_date,internal_note):
                    raise APIError('Mã yêu cầu đã được dùng cho nội dung khác. Tải lại dữ liệu trước khi tạo đơn mới.',409)
                return jsonify(ok=True,id=oid,reused=True)
            customer(db,phone,name)
            discount, redemption = 0, None
            if code:
                voucher=db.execute('SELECT * FROM redemptions WHERE code=?',(code,)).fetchone()
                if not voucher or voucher['phone']!=phone:
                    raise APIError('Voucher không thuộc khách hàng này hoặc không tồn tại.',409)
                if voucher['status']!='issued' or (voucher['expires_at'] and voucher['expires_at']<utc_stamp()):
                    raise APIError('Voucher đã hết hạn, đã sử dụng hoặc đang được giữ cho đơn khác.',409)
                snapshot=json.loads(voucher['snapshot'])
                if amount<snapshot.get('min_order',0):
                    raise APIError('Giá trị đơn chưa đạt điều kiện tối thiểu của voucher.',409)
                discount=min(amount,snapshot['value_amount'])
                redemption=voucher['id']
                db.execute("UPDATE redemptions SET status='reserved',order_id=? WHERE id=?",(oid,redemption))
            db.execute('INSERT INTO orders(id,phone,item,amount,discount,redemption_id,voucher_code,tech,due_date,internal_note) VALUES(?,?,?,?,?,?,?,?,?,?)',
                       (oid,phone,item,amount,discount,redemption,code,tech,due_date,internal_note))
        return jsonify(ok=True,id=oid)

    @app.post('/api/admin/orders/<oid>/production')
    def production_status(oid):
        d=body()
        stage=clean_text(d.get('stage'),'Tiến độ xưởng',30)
        if stage not in PRODUCTION_STAGES:
            raise APIError('Tiến độ xưởng không hợp lệ.')
        tech=clean_text(d.get('tech',''),'Công nghệ',20,False)
        if tech not in ('','ACC','SERVICE'):
            raise APIError('Loại xử lý chỉ có thể là ACC hoặc SERVICE.')
        due_date=date_value(d.get('dueDate',''),'Ngày dự kiến')
        internal_note=clean_text(d.get('internalNote',''),'Ghi chú nội bộ',1000,False)
        with database(True) as db:
            order=db.execute('SELECT status FROM orders WHERE id=?',(oid,)).fetchone()
            if not order:
                raise APIError('Không tìm thấy đơn.',404)
            if order['status'] in ('cancelled','refunded'):
                raise APIError('Đơn đã hủy/hoàn, không thể cập nhật tiến độ xưởng.',409)
            db.execute('UPDATE orders SET production_stage=?,tech=?,due_date=?,internal_note=? WHERE id=?',
                       (stage,tech,due_date,internal_note,oid))
        return jsonify(ok=True,stage=stage)

    @app.post('/api/admin/orders/<oid>/status')
    def order_status(oid):
        target=body().get('status')
        if target not in ('completed','cancelled','refunded'):
            raise APIError('Thao tác đơn không hợp lệ.')
        with database(True) as db:
            order=db.execute('SELECT * FROM orders WHERE id=?',(oid,)).fetchone()
            if not order:
                raise APIError('Không tìm thấy đơn.',404)
            if order['status']==target:
                return jsonify(ok=True,reused=True)
            if order['status']=='pending' and target in ('completed','cancelled'):
                points=(order['amount']-order['discount'])//settings(db)['vndPerPoint'] if target=='completed' else 0
                db.execute('UPDATE orders SET status=?,points=? WHERE id=?',(target,points,oid))
            elif order['status']=='completed' and target=='refunded':
                if balance(db,order['phone'])<order['points']:
                    raise APIError('Điểm của đơn đã dùng đổi quà. Hãy xử lý/thu hồi lượt đổi liên quan trước khi hoàn đơn.',409)
                db.execute("UPDATE orders SET status='refunded' WHERE id=?",(oid,))
            else:
                raise APIError('Trạng thái hiện tại không cho phép thao tác này. Hãy tải lại danh sách.',409)
            if order['redemption_id']:
                state='used' if target=='completed' else 'issued'
                db.execute('UPDATE redemptions SET status=?,order_id=? WHERE id=?',
                           (state,oid if state=='used' else None,order['redemption_id']))
        return jsonify(ok=True)

    @app.post('/api/admin/rewards')
    def save_reward():
        d=body()
        rid=clean_text(d.get('id'),'Mã quà',40)
        if not re.fullmatch(r'[a-zA-Z0-9_-]+',rid):
            raise APIError('Mã quà chỉ dùng chữ, số và dấu gạch.')
        with database(True) as db:
            old=db.execute('SELECT * FROM rewards WHERE id=?',(rid,)).fetchone()
            v=(dict(old) if old else {}) | d
            values={'id':rid,'name':clean_text(v.get('name'),'Tên quà',120),
                'cost':integer(v.get('cost'),'Điểm đổi',1,1_000_000),
                'active':integer(v.get('active',1),'Trạng thái',0,1),
                'kind':clean_text(v.get('kind','model'),'Loại quà',20),
                'description':clean_text(v.get('description',''),'Mô tả',2000,False),
                'terms':clean_text(v.get('terms',''),'Điều kiện',2000,False),
                'product_id':clean_text(v.get('product_id',''),'Sản phẩm liên kết',40,False),
                'stock':-1 if v.get('stock',-1) in (-1,'-1') else integer(v['stock'],'Số lượng còn lại',0,1_000_000),
                'per_customer_limit':integer(v.get('per_customer_limit',0),'Giới hạn mỗi khách',0,10000),
                'valid_days':integer(v.get('valid_days',0),'Số ngày dùng voucher',0,3650),
                'value_amount':integer(v.get('value_amount',0),'Giá trị voucher'),
                'min_order':integer(v.get('min_order',0),'Đơn tối thiểu'),
                'start_date':date_value(v.get('start_date',''),'Ngày bắt đầu'),
                'end_date':date_value(v.get('end_date',''),'Ngày kết thúc')}
            if values['kind'] not in REWARD_KINDS:
                raise APIError('Loại quà không hợp lệ.')
            if values['kind']=='voucher' and values['value_amount']<1:
                raise APIError('Voucher cần có giá trị giảm lớn hơn 0.')
            if values['start_date'] and values['end_date'] and values['start_date']>values['end_date']:
                raise APIError('Ngày kết thúc phải sau ngày bắt đầu.')
            if values['product_id'] and not db.execute('SELECT 1 FROM products WHERE id=?',(values['product_id'],)).fetchone():
                raise APIError('Sản phẩm liên kết không tồn tại.')
            cols=','.join(values)
            changes=','.join(k+'=excluded.'+k for k in values if k!='id')
            db.execute(f"INSERT INTO rewards({cols}) VALUES({','.join('?' for _ in values)}) ON CONFLICT(id) DO UPDATE SET {changes}",list(values.values()))
        return jsonify(ok=True)

    @app.post('/api/admin/redemptions')
    def redeem():
        d=body()
        rid=request_id(d.get('id'))
        phone=phone_number(d.get('phone'))
        rewardid=clean_text(d.get('rewardId'),'Mã quà',40)
        with database(True) as db:
            old=db.execute('SELECT * FROM redemptions WHERE id=?',(rid,)).fetchone()
            if old:
                if (old['phone'],old['reward_id'])!=(phone,rewardid):
                    raise APIError('Mã yêu cầu trùng với một lượt đổi khác.',409)
                return jsonify(ok=True,id=rid,reused=True,code=old['code'])
            reward=db.execute('SELECT * FROM rewards WHERE id=? AND active=1',(rewardid,)).fetchone()
            if not reward:
                raise APIError('Quà không còn áp dụng.',404)
            if not reward_available(reward):
                raise APIError('Quà đã hết số lượng hoặc ngoài thời gian áp dụng.',409)
            count=db.execute("SELECT COUNT(*) FROM redemptions WHERE phone=? AND reward_id=? AND status<>'cancelled'",(phone,rewardid)).fetchone()[0]
            if reward['per_customer_limit'] and count>=reward['per_customer_limit']:
                raise APIError('Khách đã đạt giới hạn đổi quà này.',409)
            if balance(db,phone)<reward['cost']:
                raise APIError('Khách chưa đủ điểm để đổi quà này.',409)
            customer(db,phone)
            code='DELTA-'+secrets.token_hex(6).upper() if reward['kind']=='voucher' else None
            status='issued' if code else 'pending'
            expires=(datetime.now(timezone.utc)+timedelta(days=reward['valid_days'])).strftime('%Y-%m-%d %H:%M:%S') if code and reward['valid_days'] else ''
            finite=int(reward['stock']>=0)
            if finite:
                db.execute('UPDATE rewards SET stock=stock-1 WHERE id=?',(rewardid,))
            db.execute('INSERT INTO redemptions(id,phone,reward_id,reward_name,cost,status,snapshot,code,expires_at,stock_reserved) VALUES(?,?,?,?,?,?,?,?,?,?)',
                       (rid,phone,rewardid,reward['name'],reward['cost'],status,json.dumps(dict(reward),ensure_ascii=False),code,expires,finite))
        return jsonify(ok=True,id=rid,code=code)

    @app.post('/api/admin/redemptions/<rid>/fulfill')
    def fulfill_redemption(rid):
        with database(True) as db:
            old=db.execute('SELECT * FROM redemptions WHERE id=?',(rid,)).fetchone()
            if not old:
                raise APIError('Không tìm thấy lượt đổi.',404)
            if old['status']=='fulfilled':
                return jsonify(ok=True,reused=True)
            if old['status']!='pending':
                raise APIError('Chỉ xác nhận trao quà đang chờ.',409)
            db.execute("UPDATE redemptions SET status='fulfilled' WHERE id=?",(rid,))
        return jsonify(ok=True)

    @app.post('/api/admin/redemptions/<rid>/cancel')
    def cancel_redemption(rid):
        with database(True) as db:
            old=db.execute('SELECT * FROM redemptions WHERE id=?',(rid,)).fetchone()
            if not old:
                raise APIError('Không tìm thấy lượt đổi.',404)
            if old['status']=='cancelled':
                return jsonify(ok=True,reused=True)
            if old['status'] in ('reserved','used'):
                raise APIError('Voucher gắn với đơn hàng. Hủy hoặc hoàn đơn liên quan trước.',409)
            db.execute("UPDATE redemptions SET status='cancelled' WHERE id=?",(rid,))
            if old['stock_reserved']:
                db.execute('UPDATE rewards SET stock=stock+1 WHERE id=? AND stock>=0',(old['reward_id'],))
        return jsonify(ok=True)

    @app.post('/api/admin/points/adjust')
    def adjust_points():
        d=body()
        aid=request_id(d.get('id'))
        phone=phone_number(d.get('phone'))
        value=d.get('delta')
        if isinstance(value,bool) or not isinstance(value,int) or not 0<abs(value)<=1_000_000:
            raise APIError('Điểm điều chỉnh cần là số nguyên khác 0, tối đa ±1.000.000.')
        reason=clean_text(d.get('reason'),'Lý do điều chỉnh',300)
        with database(True) as db:
            old=db.execute('SELECT * FROM point_adjustments WHERE id=?',(aid,)).fetchone()
            if old:
                if (old['phone'],old['delta'],old['reason'])!=(phone,value,reason):
                    raise APIError('Mã yêu cầu đã dùng cho điều chỉnh khác.',409)
                return jsonify(ok=True,reused=True)
            if balance(db,phone)+value<0:
                raise APIError('Điều chỉnh khiến điểm khả dụng bị âm.',409)
            customer(db,phone)
            db.execute('INSERT INTO point_adjustments(id,phone,delta,reason) VALUES(?,?,?,?)',(aid,phone,value,reason))
        return jsonify(ok=True)

    @app.get('/api/admin/customers/<phone>/ledger')
    def point_ledger(phone):
        phone=phone_number(phone)
        with database() as db:
            entries=[]
            for r in db.execute('SELECT * FROM orders WHERE phone=? ORDER BY rowid DESC',(phone,)):
                entries.append({'id':r['id'],'created':r['created'],'label':'Đơn: '+r['item'],'delta':r['points'] if r['status']=='completed' else 0,'status':r['status']})
            for r in db.execute('SELECT * FROM redemptions WHERE phone=? ORDER BY rowid DESC',(phone,)):
                entries.append({'id':r['id'],'created':r['created'],'label':'Đổi: '+r['reward_name'],'delta':-r['cost'] if r['status']!='cancelled' else 0,'status':r['status']})
            for r in db.execute('SELECT * FROM point_adjustments WHERE phone=? ORDER BY rowid DESC',(phone,)):
                entries.append({'id':r['id'],'created':r['created'],'label':r['reason'],'delta':r['delta'],'status':'adjusted'})
            return jsonify(phone=phone,balance=balance(db,phone),entries=sorted(entries,key=lambda x:x['created'],reverse=True))

    @app.post('/api/admin/password')
    def password():
        d=body()
        current=d.get('current','')
        new=d.get('new','')
        if not isinstance(current,str) or not isinstance(new,str) or not 12<=len(new)<=200:
            raise APIError('Mật khẩu mới cần từ 12 đến 200 ký tự.')
        with database(True) as db:
            row=db.execute('SELECT * FROM admin WHERE id=1').fetchone()
            if not check_password_hash(row['password_hash'],current):
                raise APIError('Mật khẩu hiện tại chưa đúng.',403)
            db.execute('UPDATE admin SET password_hash=?,version=version+1 WHERE id=1',(generate_password_hash(new),))
        session.clear()
        return jsonify(ok=True)

    @app.get('/api/admin/export-static')
    def export_static():
        with database() as db:
            data=store_data(db)
        content=io.BytesIO()
        with zipfile.ZipFile(content,'w',zipfile.ZIP_DEFLATED) as z:
            delta_pages=('index.html','kho-acc.html','dich-vu.html','giftcode.html','tin-tuc.html')
            for page in delta_pages:
                html=(PUBLIC_ROOT/page).read_text(encoding='utf-8').replace('src="/api/catalog.js"','src="catalog.js"')
                z.writestr(page,html)
            # Keep old bookmarks useful in static exports without exposing MORI pages.
            static_legacy={'printing.html':'dich-vu.html','products.html':'kho-acc.html','custom.html':'dich-vu.html','rewards.html':'giftcode.html','community.html':'tin-tuc.html','market.html':'kho-acc.html'}
            for old_name,new_name in static_legacy.items():
                html=(PUBLIC_ROOT/new_name).read_text(encoding='utf-8').replace('src="/api/catalog.js"','src="catalog.js"')
                z.writestr(old_name,html)
            if (PUBLIC_ROOT/'favicon.svg').is_file(): z.write(PUBLIC_ROOT/'favicon.svg','favicon.svg')
            for asset in (PUBLIC_ROOT/'assets').rglob('*'):
                if asset.is_file():
                    z.write(asset,'assets/'+asset.relative_to(PUBLIC_ROOT/'assets').as_posix())
            z.writestr('catalog.js','window.DELTA_CATALOG = '+json.dumps(data,ensure_ascii=False,indent=2)+';\n')
            paths={Path(p['image']).name for p in data['products']} | {'models.png','prints.png'}
            for product in data['products']:
                paths.update(Path(image).name for image in product.get('detailImages',[]) if isinstance(image,str))
            gift_image=str(data['settings'].get('giftHeroImage',''))
            if re.fullmatch(r'images/[a-f0-9]{32}\.webp',gift_image):
                paths.add(Path(gift_image).name)
            for name in sorted(paths):
                if (pictures/name).is_file():
                    z.write(pictures/name,'images/'+name)
            z.writestr('HUONG_DAN.txt','Giai nen toan bo thu muc roi mo index.html. Ban tinh nay chi chua gian hang, khong chua du lieu khach hang/quan tri. Khi thay doi san pham, xuat lai tu quan tri.\n')
        content.seek(0)
        return send_file(content,mimetype='application/zip',as_attachment=True,download_name='Tap_Hoa_Delta_Force_Gian_Hang_HTML.zip')

    @app.get('/api/admin/backup')
    def backup():
        # SQLite backup API provides a consistent snapshot even while WAL is active.
        content=io.BytesIO()
        with zipfile.ZipFile(content,'w',zipfile.ZIP_DEFLATED) as z:
            with tempfile.TemporaryDirectory() as folder:
                path=Path(folder)/'database.sqlite3'
                with database() as db:
                    snapshot=sqlite3.connect(path)
                    db.backup(snapshot)
                    snapshot.close()
                z.write(path,'database.sqlite3')
            for p in sorted(pictures.glob('*.webp')):
                z.write(p,'images/'+p.name)
            z.writestr('README.txt','Ban sao luu chua thong tin khach, don hang va mat khau da bam. Giu rieng. Phuc hoi: dung server, chay python restore_backup.py DUONG_DAN_ZIP.\n')
        content.seek(0)
        return send_file(content,mimetype='application/zip',as_attachment=True,download_name='Tap_Hoa_Delta_Force_Backup_'+time.strftime('%Y%m%d_%H%M%S')+'.zip')

    return app


def set_password(app, value):
    if not 12<=len(value)<=200:
        raise ValueError('Mật khẩu cần từ 12 đến 200 ký tự.')
    with app.database(True) as db:
        db.execute('INSERT INTO admin(id,password_hash) VALUES(1,?) ON CONFLICT(id) DO UPDATE SET password_hash=excluded.password_hash,version=admin.version+1',(generate_password_hash(value),))
        db.execute('DELETE FROM login_attempts')


def create_render_app():
    app = create_app()
    password = os.environ.get('SHOP_ADMIN_PASSWORD', '')
    if password:
        if not 12 <= len(password) <= 200:
            raise RuntimeError('SHOP_ADMIN_PASSWORD phải dài từ 12 đến 200 ký tự.')
        with app.database() as db:
            exists = db.execute('SELECT 1 FROM admin WHERE id=1').fetchone()
        if not exists:
            set_password(app, password)
    return app


# WSGI entry point for Render/Gunicorn.
application = create_render_app()


def main():
    parser=argparse.ArgumentParser(description='Tap Hoa Delta Force local server')
    parser.add_argument('--reset-password',action='store_true')
    parser.add_argument('--port',type=int,default=8080)
    parser.add_argument('--host',default='127.0.0.1')
    parser.add_argument('--no-browser',action='store_true')
    parser.add_argument('--data-dir')
    args=parser.parse_args()
    app=create_app(data_dir=args.data_dir)
    with app.database() as db:
        exists=db.execute('SELECT 1 FROM admin WHERE id=1').fetchone()
    if not exists or args.reset_password:
        print('\nTAP HOA DELTA FORCE — tao mat khau quan tri (toi thieu 12 ky tu).')
        print('Khi gõ mật khẩu, ký tự sẽ không hiện ra trên màn hình.\n')
        while True:
            try:
                first=getpass.getpass('Mật khẩu mới: ')
                second=getpass.getpass('Nhập lại: ')
            except (KeyboardInterrupt, EOFError):
                print('\nĐã hủy nhập mật khẩu. Chạy START_WINDOWS.bat để thử lại; gõ mật khẩu rồi Enter, không dùng Ctrl+C.')
                return
            if first==second and 12<=len(first)<=200:
                set_password(app,first)
                break
            print('Mật khẩu cần 12–200 ký tự và hai lần nhập phải giống nhau. Thử lại.')
    url=f'http://127.0.0.1:{args.port}'
    print(f'\nTAP HOA DELTA FORCE: {url}\nQUAN TRI: {url}/admin\nGiu cua so nay mo. Ctrl+C de dung.\n')
    if not args.no_browser:
        timer=threading.Timer(1.5,lambda:webbrowser.open(url))
        timer.daemon=True
        timer.start()
    from waitress import serve
    serve(app,host=args.host,port=args.port,threads=4)


if __name__=='__main__':
    main()

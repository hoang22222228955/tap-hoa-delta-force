r"""Migrate a V27 admin backup ZIP (SQLite + images) to PostgreSQL + Cloudflare R2.

Usage (PowerShell):
  $env:DATABASE_URL='postgresql://...external Render URL...?sslmode=require'
  $env:R2_ACCOUNT_ID='...'
  $env:R2_BUCKET='tap-hoa-delta-force-media'
  $env:R2_ACCESS_KEY_ID='...'
  $env:R2_SECRET_ACCESS_KEY='...'
  python migrate_backup_to_postgres_r2.py .\Tap_Hoa_Delta_Force_Backup_YYYYMMDD_HHMMSS.zip

The target database is replaced with the data from the backup.
"""
from __future__ import annotations

import os
import sqlite3
import sys
import tempfile
import zipfile
from pathlib import Path

import boto3
import psycopg
from psycopg import sql


def required(name: str) -> str:
    value = os.environ.get(name, '').strip()
    if not value:
        raise SystemExit(f'Thiếu biến môi trường {name}.')
    return value


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit('Cách dùng: python migrate_backup_to_postgres_r2.py DUONG_DAN_BACKUP.zip')
    archive = Path(sys.argv[1]).expanduser().resolve()
    if not archive.is_file():
        raise SystemExit(f'Không tìm thấy: {archive}')

    database_url = required('DATABASE_URL')
    account_id = required('R2_ACCOUNT_ID')
    bucket = required('R2_BUCKET')
    access = required('R2_ACCESS_KEY_ID')
    secret = required('R2_SECRET_ACCESS_KEY')

    with tempfile.TemporaryDirectory() as folder:
        root = Path(folder)
        with zipfile.ZipFile(archive) as z:
            names = set(z.namelist())
            if 'database.sqlite3' not in names:
                raise SystemExit('Backup này không có database.sqlite3. Hãy dùng backup V27/SQLite.')
            z.extract('database.sqlite3', root)
            image_names = [n for n in z.namelist() if n.startswith('images/') and n.endswith('.webp')]
            for n in image_names:
                z.extract(n, root)

        # Import app only to ensure the new PostgreSQL schema exists.
        os.environ['DATABASE_URL'] = database_url
        import app as shop_app  # noqa: F401

        src = sqlite3.connect(root / 'database.sqlite3')
        src.row_factory = sqlite3.Row
        dst = psycopg.connect(database_url)
        tables = [
            'admin', 'settings', 'products', 'customers', 'rewards',
            'orders', 'redemptions', 'point_adjustments', 'login_attempts'
        ]
        try:
            with dst.cursor() as cur:
                cur.execute('TRUNCATE TABLE ' + ','.join(tables) + ' RESTART IDENTITY CASCADE')
                for table in tables:
                    source_exists = src.execute(
                        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
                    ).fetchone()
                    if not source_exists:
                        continue
                    source_cols = [r[1] for r in src.execute(f'PRAGMA table_info({table})')]
                    cur.execute(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_schema='public' AND table_name=%s ORDER BY ordinal_position",
                        (table,),
                    )
                    target_cols = [r[0] for r in cur.fetchall()]
                    cols = [c for c in source_cols if c in target_cols and c != 'created_seq']
                    if not cols:
                        continue
                    rows = src.execute(
                        'SELECT ' + ','.join('"' + c.replace('"', '""') + '"' for c in cols) + f' FROM {table}'
                    ).fetchall()
                    if not rows:
                        continue
                    query = sql.SQL('INSERT INTO {} ({}) VALUES ({})').format(
                        sql.Identifier(table),
                        sql.SQL(',').join(map(sql.Identifier, cols)),
                        sql.SQL(',').join(sql.Placeholder() for _ in cols),
                    )
                    cur.executemany(query, [tuple(row[c] for c in cols) for row in rows])
                    print(f'  {table}: {len(rows)} dòng')
            dst.commit()
        except Exception:
            dst.rollback()
            raise
        finally:
            src.close()
            dst.close()

        r2 = boto3.client(
            's3',
            endpoint_url=f'https://{account_id}.r2.cloudflarestorage.com',
            region_name='auto',
            aws_access_key_id=access,
            aws_secret_access_key=secret,
        )
        for rel in image_names:
            path = root / rel
            key = Path(rel).name
            r2.put_object(
                Bucket=bucket,
                Key=key,
                Body=path.read_bytes(),
                ContentType='image/webp',
                CacheControl='public, max-age=31536000, immutable',
            )
        print(f'  R2: {len(image_names)} ảnh')

    print('\nHoàn tất. PostgreSQL và R2 đã nhận dữ liệu từ backup.')


if __name__ == '__main__':
    main()

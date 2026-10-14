"""MySQL helpers. Every query is parameterised (%s) - never string-formatted with user input."""
import os, json
from datetime import datetime, date, timedelta
from decimal import Decimal
from pathlib import Path
import mysql.connector
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / '.env')


def conn():
    return mysql.connector.connect(
        host=os.getenv('DB_HOST', 'localhost'), port=int(os.getenv('DB_PORT', '3306')),
        user=os.getenv('DB_USER', 'root'), password=os.getenv('DB_PASSWORD', ''),
        database=os.getenv('DB_NAME', 'workforce_portal'))


def clean(v):
    if isinstance(v, datetime): return v.isoformat(timespec='seconds')
    if isinstance(v, date): return v.isoformat()
    if isinstance(v, Decimal): return float(v)
    if isinstance(v, timedelta): return str(v)
    return v


def q(sql, params=()):
    c = conn(); cur = c.cursor(dictionary=True)
    try:
        cur.execute(sql, tuple(params))
        return [{k: clean(v) for k, v in r.items()} for r in cur.fetchall()]
    finally:
        cur.close(); c.close()


def one(sql, params=()):
    r = q(sql, params)
    return r[0] if r else None


def ex(sql, params=()):
    c = conn(); cur = c.cursor()
    try:
        cur.execute(sql, tuple(params)); c.commit(); return cur.lastrowid
    finally:
        cur.close(); c.close()


def settings():
    return {r['k']: r['v'] for r in q('SELECT k,v FROM settings')}


def jsetting(key, default=None):
    try: return json.loads(settings().get(key, ''))
    except ValueError: return default

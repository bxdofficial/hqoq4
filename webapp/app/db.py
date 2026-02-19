import os
import sqlite3
from contextlib import contextmanager

DB_PATH = os.getenv('APP_DB_PATH', 'hoqouqi.db')

SCHEMA = '''
CREATE TABLE IF NOT EXISTS users (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  email TEXT UNIQUE NOT NULL,
  password_hash TEXT NOT NULL,
  user_type TEXT NOT NULL CHECK (user_type IN ('client','lawyer','admin')),
  full_name TEXT NOT NULL,
  is_verified INTEGER DEFAULT 0,
  is_active INTEGER DEFAULT 1,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS lawyers (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER UNIQUE NOT NULL,
  bar_registration_number TEXT UNIQUE,
  bar_level TEXT,
  governorate TEXT,
  city TEXT,
  bio TEXT,
  min_consultation_fee INTEGER DEFAULT 400,
  is_verified INTEGER DEFAULT 0,
  FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS cases (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  client_user_id INTEGER NOT NULL,
  lawyer_user_id INTEGER,
  title TEXT NOT NULL,
  case_type TEXT NOT NULL,
  description TEXT NOT NULL,
  status TEXT DEFAULT 'pending',
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (client_user_id) REFERENCES users(id),
  FOREIGN KEY (lawyer_user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS payments (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  case_id INTEGER NOT NULL,
  client_user_id INTEGER NOT NULL,
  lawyer_user_id INTEGER NOT NULL,
  amount REAL NOT NULL,
  status TEXT DEFAULT 'pending',
  escrow_status TEXT DEFAULT 'held',
  transaction_ref TEXT UNIQUE,
  notes TEXT,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (case_id) REFERENCES cases(id)
);

CREATE TABLE IF NOT EXISTS messages (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  case_id INTEGER NOT NULL,
  sender_user_id INTEGER NOT NULL,
  receiver_user_id INTEGER NOT NULL,
  content TEXT NOT NULL,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (case_id) REFERENCES cases(id)
);

CREATE TABLE IF NOT EXISTS case_documents (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  case_id INTEGER NOT NULL,
  uploaded_by_user_id INTEGER NOT NULL,
  original_filename TEXT NOT NULL,
  storage_key TEXT UNIQUE NOT NULL,
  mime_type TEXT NOT NULL,
  size_bytes INTEGER NOT NULL,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (case_id) REFERENCES cases(id) ON DELETE CASCADE,
  FOREIGN KEY (uploaded_by_user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS lawyer_verification_requests (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  lawyer_user_id INTEGER NOT NULL,
  bar_registration_number TEXT NOT NULL,
  status TEXT DEFAULT 'submitted' CHECK (status IN ('submitted','under_review','approved','rejected')),
  review_notes TEXT,
  reviewed_by_user_id INTEGER,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  reviewed_at DATETIME,
  FOREIGN KEY (lawyer_user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS audit_logs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  actor_user_id INTEGER,
  action TEXT NOT NULL,
  target_type TEXT,
  target_id INTEGER,
  metadata TEXT,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (actor_user_id) REFERENCES users(id)
);
'''


def init_db() -> None:
    with sqlite3.connect(DB_PATH) as conn:
        conn.executescript(SCHEMA)
        # safe evolutions for existing DBs
        conn.execute('CREATE INDEX IF NOT EXISTS idx_cases_client ON cases(client_user_id)')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_cases_lawyer ON cases(lawyer_user_id)')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_messages_case ON messages(case_id)')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_payments_case ON payments(case_id)')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_case_documents_case ON case_documents(case_id)')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_audit_actor ON audit_logs(actor_user_id)')
        conn.execute('CREATE INDEX IF NOT EXISTS idx_verification_status ON lawyer_verification_requests(status)')

        cols = [row[1] for row in conn.execute('PRAGMA table_info(payments)').fetchall()]
        if 'transaction_ref' not in cols:
            conn.execute('ALTER TABLE payments ADD COLUMN transaction_ref TEXT')
        if 'notes' not in cols:
            conn.execute('ALTER TABLE payments ADD COLUMN notes TEXT')
        if 'updated_at' not in cols:
            conn.execute("ALTER TABLE payments ADD COLUMN updated_at DATETIME DEFAULT CURRENT_TIMESTAMP")
        conn.commit()


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()

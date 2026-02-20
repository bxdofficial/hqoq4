import hashlib
import hmac
import json
import os
import secrets
import time
import urllib.error
import urllib.request
from collections import defaultdict, deque
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, Request, Form, HTTPException, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from app.db import init_db, get_conn
from app.auth import hash_password, verify_password, create_session_token, verify_session_token, get_secret_key

app = FastAPI(title='Hoqouqi Python Edition')
app.mount('/static', StaticFiles(directory='static'), name='static')
templates = Jinja2Templates(directory='templates')

RATE_BUCKETS: dict[str, deque] = defaultdict(deque)
LOGIN_WINDOW_SECONDS = 60
LOGIN_MAX_ATTEMPTS = 8
AI_DEFAULT_POLICY = [
    'قدّم معلومات قانونية عامة داخل مصر فقط ولا تقدّم تمثيلاً قانونياً.',
    'لا تقدّم رأياً قانونياً نهائياً أو وعداً بنتيجة القضية.',
    'عند الحاجة يجب توجيه المستخدم لمحامٍ مرخّص داخل المنصة.',
    'احمِ خصوصية البيانات وتجنب طلب بيانات حساسة غير لازمة.',
]

UPLOADS_DIR = Path(os.getenv('APP_UPLOADS_DIR', 'uploads'))
MAX_CASE_DOCUMENT_SIZE = int(os.getenv('MAX_CASE_DOCUMENT_SIZE_BYTES', str(10 * 1024 * 1024)))
ALLOWED_CASE_DOCUMENT_MIME_TYPES = {
    'application/pdf',
    'image/png',
    'image/jpeg',
    'application/msword',
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
}
SIGNED_URL_TTL_SECONDS = int(os.getenv('APP_SIGNED_URL_TTL_SECONDS', '600'))


def is_secure_cookie_enabled() -> bool:
    return os.getenv('APP_COOKIE_SECURE', 'true').lower() == 'true'


def _client_ip(request: Request) -> str:
    return request.headers.get('x-forwarded-for', request.client.host if request.client else 'unknown').split(',')[0].strip()


def _check_rate_limit(key: str, limit: int = LOGIN_MAX_ATTEMPTS, window_s: int = LOGIN_WINDOW_SECONDS) -> None:
    now = time.time()
    q = RATE_BUCKETS[key]
    while q and q[0] < now - window_s:
        q.popleft()
    if len(q) >= limit:
        raise HTTPException(status_code=429, detail='Too many requests, please try again later')
    q.append(now)


def issue_csrf_token() -> str:
    return secrets.token_urlsafe(32)


def verify_csrf(request: Request, form_token: str) -> None:
    cookie_token = request.cookies.get('hq_csrf')
    if not cookie_token or not form_token or cookie_token != form_token:
        raise HTTPException(status_code=403, detail='CSRF validation failed')


def current_user(request: Request):
    token = request.cookies.get('hq_session')
    if not token:
        return None
    return verify_session_token(token)


def require_user(request: Request, allowed=None):
    user = current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail='Authentication required')
    if allowed and user['user_type'] not in allowed:
        raise HTTPException(status_code=403, detail='Forbidden')
    return user


def log_action(actor_user_id: int | None, action: str, target_type: str | None = None, target_id: int | None = None, metadata: dict | None = None):
    with get_conn() as conn:
        conn.execute(
            'INSERT INTO audit_logs (actor_user_id, action, target_type, target_id, metadata) VALUES (?, ?, ?, ?, ?)',
            (actor_user_id, action, target_type, target_id, json.dumps(metadata or {}, ensure_ascii=False)),
        )


def is_case_participant(conn, case_id: int, user_id: int) -> bool:
    case = conn.execute('SELECT client_user_id, lawyer_user_id FROM cases WHERE id = ?', (case_id,)).fetchone()
    if not case:
        return False
    return user_id in {case['client_user_id'], case['lawyer_user_id']}


def _sanitize_filename(filename: str) -> str:
    base = Path(filename).name.strip()
    return base or 'document'


def _build_case_document_storage_key(case_id: int, original_filename: str) -> str:
    ext = Path(original_filename).suffix[:16]
    return f"case_{case_id}/{secrets.token_urlsafe(18)}{ext}"


def _sign_download_token(document_id: int, user_id: int, expires_at: int) -> str:
    payload = f'{document_id}:{user_id}:{expires_at}'
    return hmac.new(get_secret_key().encode(), payload.encode(), hashlib.sha256).hexdigest()


def _build_signed_download_url(document_id: int, user_id: int, ttl_s: int = SIGNED_URL_TTL_SECONDS) -> str:
    expires_at = int(time.time()) + ttl_s
    signature = _sign_download_token(document_id, user_id, expires_at)
    return f'/api/case-documents/{document_id}/download?expires={expires_at}&sig={signature}'


def _validate_case_document_upload(upload: UploadFile, data: bytes) -> None:
    mime = (upload.content_type or '').lower().strip()
    if mime not in ALLOWED_CASE_DOCUMENT_MIME_TYPES:
        raise HTTPException(status_code=400, detail='Unsupported file type')
    size = len(data)
    if size == 0:
        raise HTTPException(status_code=400, detail='Uploaded file is empty')
    if size > MAX_CASE_DOCUMENT_SIZE:
        raise HTTPException(status_code=400, detail='File size exceeds allowed limit')


def _resolve_case_document_path(storage_key: str) -> Path:
    path = (UPLOADS_DIR / storage_key).resolve()
    root = UPLOADS_DIR.resolve()
    if root not in path.parents and path != root:
        raise HTTPException(status_code=400, detail='Invalid storage key')
    return path


def _render_with_csrf(template_name: str, request: Request, context: dict | None = None):
    payload = {'request': request, 'user': current_user(request)}
    if context:
        payload.update(context)
    payload.setdefault('user', current_user(request))
    csrf_token = issue_csrf_token()
    payload['csrf_token'] = csrf_token
    response = templates.TemplateResponse(template_name, payload)
    response.set_cookie('hq_csrf', csrf_token, httponly=True, samesite='lax', secure=is_secure_cookie_enabled(), max_age=3600)
    return response


class CaseCreatePayload(BaseModel):
    title: str = Field(min_length=3, max_length=180)
    case_type: str = Field(min_length=2, max_length=80)
    description: str = Field(min_length=10, max_length=5000)
    client_user_id: int | None = None


class CaseAssignPayload(BaseModel):
    lawyer_user_id: int


class CaseStatusPayload(BaseModel):
    status: Literal['pending', 'accepted', 'rejected', 'in_progress', 'completed', 'cancelled']


class LawyerReviewPayload(BaseModel):
    decision: Literal['approved', 'rejected']
    notes: str | None = Field(default=None, max_length=1000)


class PaymentCreatePayload(BaseModel):
    case_id: int
    amount: float = Field(gt=0)


class PaymentActionPayload(BaseModel):
    transaction_ref: str | None = Field(default=None, max_length=120)
    notes: str | None = Field(default=None, max_length=1000)


class MessagePayload(BaseModel):
    case_id: int
    receiver_user_id: int
    content: str = Field(min_length=1, max_length=3000)


class CaseDocumentUploadResponse(BaseModel):
    id: int
    case_id: int
    original_filename: str
    mime_type: str
    size_bytes: int
    download_url: str


class AIAssistPayload(BaseModel):
    question: str = Field(min_length=5, max_length=3000)
    policy_rules: list[str] | None = None


@app.on_event('startup')
def startup() -> None:
    get_secret_key()
    init_db()
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)


@app.get('/', response_class=HTMLResponse)
def home(request: Request):
    user = current_user(request)
    return templates.TemplateResponse('index.html', {'request': request, 'user': user})


@app.get('/register', response_class=HTMLResponse)
def register_page(request: Request):
    return _render_with_csrf('register.html', request)


@app.post('/register')
def register(
    request: Request,
    csrf_token: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    full_name: str = Form(...),
    user_type: str = Form(...),
    bar_registration_number: str = Form(''),
):
    verify_csrf(request, csrf_token)
    _check_rate_limit(f"register:{_client_ip(request)}", limit=5, window_s=60)

    if user_type not in {'client', 'lawyer'}:
        raise HTTPException(status_code=400, detail='Invalid user type')

    if len(password) < 8:
        raise HTTPException(status_code=400, detail='Password must be at least 8 characters')

    with get_conn() as conn:
        exists = conn.execute('SELECT id FROM users WHERE email = ?', (email.strip().lower(),)).fetchone()
        if exists:
            raise HTTPException(status_code=400, detail='Email already exists')

        cur = conn.execute(
            'INSERT INTO users (email, password_hash, user_type, full_name) VALUES (?, ?, ?, ?)',
            (email.strip().lower(), hash_password(password), user_type, full_name.strip()),
        )
        user_id = cur.lastrowid

        if user_type == 'lawyer':
            conn.execute(
                'INSERT INTO lawyers (user_id, bar_registration_number) VALUES (?, ?)',
                (user_id, bar_registration_number.strip()),
            )
            conn.execute(
                'INSERT INTO lawyer_verification_requests (lawyer_user_id, bar_registration_number) VALUES (?, ?)',
                (user_id, bar_registration_number.strip() or 'PENDING'),
            )

    log_action(user_id, 'user.registered', 'user', user_id, {'user_type': user_type})
    return RedirectResponse('/login', status_code=303)


@app.get('/login', response_class=HTMLResponse)
def login_page(request: Request):
    return _render_with_csrf('login.html', request)


@app.post('/login')
def login(
    request: Request,
    csrf_token: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
):
    verify_csrf(request, csrf_token)
    _check_rate_limit(f"login:{_client_ip(request)}")

    with get_conn() as conn:
        user = conn.execute('SELECT * FROM users WHERE email = ? AND is_active = 1', (email.strip().lower(),)).fetchone()

    if not user or not verify_password(password, user['password_hash']):
        raise HTTPException(status_code=401, detail='Invalid credentials')

    token = create_session_token(user['id'], user['user_type'])
    response = RedirectResponse('/dashboard', status_code=303)
    response.set_cookie(
        'hq_session',
        token,
        httponly=True,
        samesite='lax',
        secure=is_secure_cookie_enabled(),
        max_age=60 * 60 * 24 * 7,
    )
    log_action(user['id'], 'user.login', 'user', user['id'])
    return response


@app.get('/logout')
def logout(request: Request):
    user = current_user(request)
    response = RedirectResponse('/', status_code=303)
    response.delete_cookie('hq_session')
    response.delete_cookie('hq_csrf')
    if user:
        log_action(user['user_id'], 'user.logout', 'user', user['user_id'])
    return response


@app.get('/dashboard', response_class=HTMLResponse)
def dashboard(request: Request):
    user = require_user(request, ['client', 'lawyer', 'admin'])
    with get_conn() as conn:
        me = conn.execute('SELECT id, full_name, email, user_type, is_verified FROM users WHERE id = ?', (user['user_id'],)).fetchone()
        cases = conn.execute(
            'SELECT * FROM cases WHERE client_user_id = ? OR lawyer_user_id = ? ORDER BY id DESC LIMIT 20',
            (user['user_id'], user['user_id']),
        ).fetchall()
    return templates.TemplateResponse('dashboard.html', {'request': request, 'user': dict(me), 'cases': [dict(x) for x in cases]})


@app.get('/search', response_class=HTMLResponse)
def search_page(request: Request):
    with get_conn() as conn:
        lawyers = conn.execute(
            '''
            SELECT u.id, u.full_name, l.bar_registration_number, l.min_consultation_fee, l.city, l.governorate, u.is_verified
            FROM users u JOIN lawyers l ON l.user_id = u.id
            WHERE u.user_type = 'lawyer' AND u.is_active = 1
            ORDER BY u.is_verified DESC, u.id DESC
            '''
        ).fetchall()
    return templates.TemplateResponse('search.html', {'request': request, 'lawyers': [dict(x) for x in lawyers], 'user': current_user(request)})


@app.get('/api/health')
def api_health():
    return {
        'success': True,
        'service': 'hoqouqi-python',
        'status': 'healthy',
        'secure_cookie': is_secure_cookie_enabled(),
    }


@app.get('/api/config/health')
def config_health(request: Request):
    user = require_user(request, ['admin'])
    return {
        'success': True,
        'data': {
            'cookie_secure': is_secure_cookie_enabled(),
            'db_path': os.getenv('APP_DB_PATH', 'hoqouqi.db'),
            'ai_configured': bool(os.getenv('GEMINI_API_KEY')),
            'secret_loaded': bool(get_secret_key()),
            'viewer': user,
        },
    }


@app.post('/api/cases')
def create_case(request: Request, payload: CaseCreatePayload):
    user = require_user(request, ['client', 'admin'])

    client_user_id = payload.client_user_id or user['user_id']
    if user['user_type'] == 'client' and client_user_id != user['user_id']:
        raise HTTPException(status_code=403, detail='Forbidden')

    with get_conn() as conn:
        cur = conn.execute(
            'INSERT INTO cases (client_user_id, title, case_type, description) VALUES (?, ?, ?, ?)',
            (client_user_id, payload.title.strip(), payload.case_type.strip(), payload.description.strip()),
        )
        case_id = cur.lastrowid
        row = conn.execute('SELECT * FROM cases WHERE id = ?', (case_id,)).fetchone()

    log_action(user['user_id'], 'case.created', 'case', case_id)
    return JSONResponse({'success': True, 'data': dict(row)}, status_code=201)


@app.get('/api/cases')
def list_cases(request: Request):
    user = require_user(request, ['client', 'lawyer', 'admin'])
    with get_conn() as conn:
        if user['user_type'] == 'admin':
            rows = conn.execute('SELECT * FROM cases ORDER BY id DESC LIMIT 100').fetchall()
        else:
            rows = conn.execute(
                'SELECT * FROM cases WHERE client_user_id = ? OR lawyer_user_id = ? ORDER BY id DESC LIMIT 100',
                (user['user_id'], user['user_id']),
            ).fetchall()
    return {'success': True, 'data': [dict(x) for x in rows]}


@app.post('/api/cases/{case_id}/assign')
def assign_case(request: Request, case_id: int, payload: CaseAssignPayload):
    user = require_user(request, ['admin'])
    with get_conn() as conn:
        case = conn.execute('SELECT * FROM cases WHERE id = ?', (case_id,)).fetchone()
        lawyer = conn.execute('SELECT id, user_type, is_active, is_verified FROM users WHERE id = ?', (payload.lawyer_user_id,)).fetchone()
        if not case:
            raise HTTPException(status_code=404, detail='Case not found')
        if not lawyer or lawyer['user_type'] != 'lawyer' or lawyer['is_active'] != 1:
            raise HTTPException(status_code=400, detail='Invalid lawyer')

        conn.execute('UPDATE cases SET lawyer_user_id = ?, status = ? WHERE id = ?', (payload.lawyer_user_id, 'accepted', case_id))

    log_action(user['user_id'], 'case.assigned', 'case', case_id, {'lawyer_user_id': payload.lawyer_user_id})
    return {'success': True, 'message': 'Case assigned'}


@app.post('/api/cases/{case_id}/status')
def update_case_status(request: Request, case_id: int, payload: CaseStatusPayload):
    user = require_user(request, ['client', 'lawyer', 'admin'])
    with get_conn() as conn:
        case = conn.execute('SELECT * FROM cases WHERE id = ?', (case_id,)).fetchone()
        if not case:
            raise HTTPException(status_code=404, detail='Case not found')

        if user['user_type'] != 'admin' and user['user_id'] not in {case['client_user_id'], case['lawyer_user_id']}:
            raise HTTPException(status_code=403, detail='Forbidden')

        conn.execute('UPDATE cases SET status = ? WHERE id = ?', (payload.status, case_id))

    log_action(user['user_id'], 'case.status_updated', 'case', case_id, {'status': payload.status})
    return {'success': True, 'message': 'Case status updated'}


@app.post('/api/payments')
def create_payment(request: Request, payload: PaymentCreatePayload):
    user = require_user(request, ['client', 'admin'])
    with get_conn() as conn:
        case = conn.execute('SELECT * FROM cases WHERE id = ?', (payload.case_id,)).fetchone()
        if not case:
            raise HTTPException(status_code=404, detail='Case not found')
        if user['user_type'] == 'client' and case['client_user_id'] != user['user_id']:
            raise HTTPException(status_code=403, detail='Forbidden')
        if not case['lawyer_user_id']:
            raise HTTPException(status_code=400, detail='Assign a lawyer before creating payment')

        cur = conn.execute(
            'INSERT INTO payments (case_id, client_user_id, lawyer_user_id, amount, status, escrow_status) VALUES (?, ?, ?, ?, ?, ?)',
            (payload.case_id, case['client_user_id'], case['lawyer_user_id'], payload.amount, 'pending', 'held'),
        )
        payment_id = cur.lastrowid
        payment = conn.execute('SELECT * FROM payments WHERE id = ?', (payment_id,)).fetchone()

    log_action(user['user_id'], 'payment.created', 'payment', payment_id, {'case_id': payload.case_id})
    return JSONResponse({'success': True, 'data': dict(payment)}, status_code=201)


@app.get('/api/payments')
def list_payments(request: Request):
    user = require_user(request, ['client', 'lawyer', 'admin'])
    with get_conn() as conn:
        if user['user_type'] == 'admin':
            rows = conn.execute('SELECT * FROM payments ORDER BY id DESC LIMIT 100').fetchall()
        elif user['user_type'] == 'client':
            rows = conn.execute('SELECT * FROM payments WHERE client_user_id = ? ORDER BY id DESC LIMIT 100', (user['user_id'],)).fetchall()
        else:
            rows = conn.execute('SELECT * FROM payments WHERE lawyer_user_id = ? ORDER BY id DESC LIMIT 100', (user['user_id'],)).fetchall()
    return {'success': True, 'data': [dict(x) for x in rows]}


@app.post('/api/payments/{payment_id}/process')
def process_payment(request: Request, payment_id: int, payload: PaymentActionPayload):
    user = require_user(request, ['admin'])
    with get_conn() as conn:
        payment = conn.execute('SELECT * FROM payments WHERE id = ?', (payment_id,)).fetchone()
        if not payment:
            raise HTTPException(status_code=404, detail='Payment not found')

        txn_ref = payload.transaction_ref or f'TXN-{payment_id}-{int(time.time())}'
        conn.execute(
            'UPDATE payments SET status = ?, transaction_ref = ?, notes = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?',
            ('paid', txn_ref, payload.notes, payment_id),
        )

    log_action(user['user_id'], 'payment.processed', 'payment', payment_id, {'transaction_ref': payload.transaction_ref})
    return {'success': True, 'message': 'Payment processed'}


@app.post('/api/payments/{payment_id}/release')
def release_payment(request: Request, payment_id: int, payload: PaymentActionPayload):
    user = require_user(request, ['admin'])
    with get_conn() as conn:
        payment = conn.execute('SELECT * FROM payments WHERE id = ?', (payment_id,)).fetchone()
        if not payment:
            raise HTTPException(status_code=404, detail='Payment not found')
        if payment['status'] != 'paid':
            raise HTTPException(status_code=400, detail='Only paid payments can be released')

        conn.execute(
            'UPDATE payments SET escrow_status = ?, notes = COALESCE(?, notes), updated_at = CURRENT_TIMESTAMP WHERE id = ?',
            ('released', payload.notes, payment_id),
        )

    log_action(user['user_id'], 'payment.released', 'payment', payment_id)
    return {'success': True, 'message': 'Payment released to lawyer'}


@app.post('/api/payments/{payment_id}/refund')
def refund_payment(request: Request, payment_id: int, payload: PaymentActionPayload):
    user = require_user(request, ['admin'])
    with get_conn() as conn:
        payment = conn.execute('SELECT * FROM payments WHERE id = ?', (payment_id,)).fetchone()
        if not payment:
            raise HTTPException(status_code=404, detail='Payment not found')

        conn.execute(
            'UPDATE payments SET status = ?, escrow_status = ?, notes = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?',
            ('refunded', 'returned', payload.notes, payment_id),
        )

    log_action(user['user_id'], 'payment.refunded', 'payment', payment_id)
    return {'success': True, 'message': 'Payment refunded'}


@app.post('/api/messages')
def send_message(request: Request, payload: MessagePayload):
    user = require_user(request, ['client', 'lawyer', 'admin'])

    with get_conn() as conn:
        case = conn.execute('SELECT * FROM cases WHERE id = ?', (payload.case_id,)).fetchone()
        if not case:
            raise HTTPException(status_code=404, detail='Case not found')

        if user['user_type'] != 'admin' and user['user_id'] not in {case['client_user_id'], case['lawyer_user_id']}:
            raise HTTPException(status_code=403, detail='Only case participants can send messages')

        if user['user_type'] != 'admin' and payload.receiver_user_id not in {case['client_user_id'], case['lawyer_user_id']}:
            raise HTTPException(status_code=400, detail='Receiver must be case participant')

        cur = conn.execute(
            'INSERT INTO messages (case_id, sender_user_id, receiver_user_id, content) VALUES (?, ?, ?, ?)',
            (payload.case_id, user['user_id'], payload.receiver_user_id, payload.content.strip()),
        )
        msg_id = cur.lastrowid

    log_action(user['user_id'], 'message.sent', 'message', msg_id, {'case_id': payload.case_id})
    return JSONResponse({'success': True, 'data': {'message_id': msg_id}}, status_code=201)


@app.get('/api/messages/{case_id}')
def list_messages(request: Request, case_id: int):
    user = require_user(request, ['client', 'lawyer', 'admin'])
    with get_conn() as conn:
        if user['user_type'] != 'admin' and not is_case_participant(conn, case_id, user['user_id']):
            raise HTTPException(status_code=403, detail='Forbidden')
        rows = conn.execute(
            'SELECT * FROM messages WHERE case_id = ? ORDER BY id ASC LIMIT 500',
            (case_id,),
        ).fetchall()
    return {'success': True, 'data': [dict(x) for x in rows]}


@app.post('/api/cases/{case_id}/documents')
async def upload_case_document(request: Request, case_id: int, file: UploadFile = File(...)):
    user = require_user(request, ['client', 'lawyer', 'admin'])
    data = await file.read()
    _validate_case_document_upload(file, data)
    filename = _sanitize_filename(file.filename or 'document')

    with get_conn() as conn:
        case = conn.execute('SELECT id FROM cases WHERE id = ?', (case_id,)).fetchone()
        if not case:
            raise HTTPException(status_code=404, detail='Case not found')
        if user['user_type'] != 'admin' and not is_case_participant(conn, case_id, user['user_id']):
            raise HTTPException(status_code=403, detail='Only case participants can upload documents')

        storage_key = _build_case_document_storage_key(case_id, filename)
        disk_path = _resolve_case_document_path(storage_key)
        disk_path.parent.mkdir(parents=True, exist_ok=True)
        disk_path.write_bytes(data)

        try:
            cur = conn.execute(
                '''
                INSERT INTO case_documents (case_id, uploaded_by_user_id, original_filename, storage_key, mime_type, size_bytes)
                VALUES (?, ?, ?, ?, ?, ?)
                ''',
                (case_id, user['user_id'], filename, storage_key, (file.content_type or '').lower().strip(), len(data)),
            )
        except Exception:
            if disk_path.exists():
                disk_path.unlink()
            raise

        doc_id = cur.lastrowid

    log_action(user['user_id'], 'case.document.uploaded', 'case_document', doc_id, {'case_id': case_id, 'mime_type': file.content_type, 'size_bytes': len(data)})
    return JSONResponse(
        {
            'success': True,
            'data': CaseDocumentUploadResponse(
                id=doc_id,
                case_id=case_id,
                original_filename=filename,
                mime_type=(file.content_type or '').lower().strip(),
                size_bytes=len(data),
                download_url=_build_signed_download_url(doc_id, user['user_id']),
            ).model_dump(),
        },
        status_code=201,
    )


@app.get('/api/cases/{case_id}/documents')
def list_case_documents(request: Request, case_id: int):
    user = require_user(request, ['client', 'lawyer', 'admin'])
    with get_conn() as conn:
        case = conn.execute('SELECT id FROM cases WHERE id = ?', (case_id,)).fetchone()
        if not case:
            raise HTTPException(status_code=404, detail='Case not found')
        if user['user_type'] != 'admin' and not is_case_participant(conn, case_id, user['user_id']):
            raise HTTPException(status_code=403, detail='Only case participants can view documents')

        rows = conn.execute(
            '''
            SELECT id, case_id, uploaded_by_user_id, original_filename, mime_type, size_bytes, created_at
            FROM case_documents
            WHERE case_id = ?
            ORDER BY id DESC
            ''',
            (case_id,),
        ).fetchall()

    data = []
    for row in rows:
        item = dict(row)
        item['download_url'] = _build_signed_download_url(item['id'], user['user_id'])
        data.append(item)
    return {'success': True, 'data': data}


@app.get('/api/case-documents/{document_id}/download')
def download_case_document(request: Request, document_id: int, expires: int, sig: str):
    user = require_user(request, ['client', 'lawyer', 'admin'])

    if expires < int(time.time()):
        raise HTTPException(status_code=403, detail='Signed URL expired')

    expected_sig = _sign_download_token(document_id, user['user_id'], expires)
    if not hmac.compare_digest(sig, expected_sig):
        raise HTTPException(status_code=403, detail='Invalid signed URL')

    with get_conn() as conn:
        row = conn.execute('SELECT * FROM case_documents WHERE id = ?', (document_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail='Document not found')
        if user['user_type'] != 'admin' and not is_case_participant(conn, row['case_id'], user['user_id']):
            raise HTTPException(status_code=403, detail='Only case participants can download documents')

    path = _resolve_case_document_path(row['storage_key'])
    if not path.exists():
        raise HTTPException(status_code=404, detail='Stored file missing')

    log_action(user['user_id'], 'case.document.downloaded', 'case_document', document_id, {'case_id': row['case_id']})
    return FileResponse(path, media_type=row['mime_type'], filename=row['original_filename'])


@app.get('/api/admin/lawyer-verifications')
def list_verifications(request: Request, status: str = 'submitted'):
    require_user(request, ['admin'])
    with get_conn() as conn:
        rows = conn.execute(
            '''
            SELECT vr.*, u.full_name, u.email
            FROM lawyer_verification_requests vr
            JOIN users u ON u.id = vr.lawyer_user_id
            WHERE vr.status = ?
            ORDER BY vr.id ASC
            ''',
            (status,),
        ).fetchall()
    return {'success': True, 'data': [dict(x) for x in rows]}


@app.post('/api/admin/lawyer-verifications/{request_id}/review')
def review_verification(request: Request, request_id: int, payload: LawyerReviewPayload):
    admin = require_user(request, ['admin'])

    with get_conn() as conn:
        req = conn.execute('SELECT * FROM lawyer_verification_requests WHERE id = ?', (request_id,)).fetchone()
        if not req:
            raise HTTPException(status_code=404, detail='Request not found')

        conn.execute(
            '''
            UPDATE lawyer_verification_requests
            SET status = ?, review_notes = ?, reviewed_by_user_id = ?, reviewed_at = CURRENT_TIMESTAMP
            WHERE id = ?
            ''',
            (payload.decision, payload.notes, admin['user_id'], request_id),
        )
        verified = 1 if payload.decision == 'approved' else 0
        conn.execute('UPDATE users SET is_verified = ? WHERE id = ?', (verified, req['lawyer_user_id']))

    log_action(admin['user_id'], 'lawyer.verification.reviewed', 'verification_request', request_id, {'decision': payload.decision})
    return {'success': True, 'message': 'Review saved'}


@app.get('/api/admin/overview')
def admin_overview(request: Request):
    require_user(request, ['admin'])
    with get_conn() as conn:
        users = conn.execute('SELECT user_type, COUNT(*) c FROM users GROUP BY user_type').fetchall()
        pending_verifications = conn.execute("SELECT COUNT(*) c FROM lawyer_verification_requests WHERE status IN ('submitted','under_review')").fetchone()['c']
        open_cases = conn.execute("SELECT COUNT(*) c FROM cases WHERE status IN ('pending','accepted','in_progress')").fetchone()['c']
        pending_payments = conn.execute("SELECT COUNT(*) c FROM payments WHERE status IN ('pending','paid') AND escrow_status = 'held'").fetchone()['c']
    return {
        'success': True,
        'data': {
            'users_by_type': {row['user_type']: row['c'] for row in users},
            'pending_verifications': pending_verifications,
            'open_cases': open_cases,
            'pending_payments_in_escrow': pending_payments,
        },
    }


@app.get('/api/admin/audit-logs')
def admin_audit_logs(request: Request, limit: int = 100):
    require_user(request, ['admin'])
    safe_limit = min(max(limit, 1), 500)
    with get_conn() as conn:
        rows = conn.execute(
            'SELECT * FROM audit_logs ORDER BY id DESC LIMIT ?',
            (safe_limit,),
        ).fetchall()
    return {'success': True, 'data': [dict(x) for x in rows]}


def _load_ai_policy_rules(extra_rules: list[str] | None) -> list[str]:
    env_rules = [x.strip() for x in os.getenv('AI_POLICY_RULES', '').split('\n') if x.strip()]
    merged = AI_DEFAULT_POLICY + env_rules + (extra_rules or [])
    # de-duplicate while preserving order
    seen = set()
    result = []
    for rule in merged:
        if rule not in seen:
            seen.add(rule)
            result.append(rule)
    return result[:20]


def _generate_ai_text(question: str, policy_rules: list[str]) -> str:
    api_key = os.getenv('GEMINI_API_KEY', '').strip()
    model = os.getenv('GEMINI_MODEL', 'gemini-1.5-flash')

    if not api_key:
        return (
            'تنبيه: هذه معلومات عامة وليست استشارة قانونية نهائية. '
            'لا يوجد مفتاح AI مفعّل حالياً، لذا تم تطبيق إرشاد قائم على اللوائح المحددة فقط.\n\n'
            + '\n'.join([f'- {r}' for r in policy_rules])
            + '\n\nسؤالك: '
            + question
        )

    policy_block = '\n'.join([f'{i+1}) {r}' for i, r in enumerate(policy_rules)])
    prompt = (
        'أنت مساعد امتثال قانوني داخل منصة حقوقي في مصر. '\
        'التزم بالقواعد التالية حرفياً ولا تخرج عنها:\n'
        f'{policy_block}\n\n'
        'أجب بالعربية الفصحى المختصرة. '\
        'أي طلب رأي قانوني نهائي أو توقع حكم: ارفض بلطف ووجّه المستخدم لمحامٍ مرخص.\n\n'
        f'سؤال المستخدم: {question}'
    )

    body = {
        'contents': [{'role': 'user', 'parts': [{'text': prompt}]}],
        'generationConfig': {'temperature': 0.2, 'maxOutputTokens': 500},
    }

    req = urllib.request.Request(
        url=f'https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}',
        data=json.dumps(body).encode('utf-8'),
        headers={'Content-Type': 'application/json'},
        method='POST',
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as response:
            payload = json.loads(response.read().decode('utf-8'))
            candidates = payload.get('candidates', [])
            if not candidates:
                raise RuntimeError('No candidates from AI provider')
            text = candidates[0].get('content', {}).get('parts', [{}])[0].get('text', '').strip()
            if not text:
                raise RuntimeError('Empty AI response')
            return text
    except (urllib.error.URLError, RuntimeError, KeyError, json.JSONDecodeError) as exc:
        return (
            'تعذّر الوصول إلى مزود الذكاء الاصطناعي الآن. '\
            'هذه إرشادات عامة وفق سياسة المنصة فقط:\n'
            + '\n'.join([f'- {r}' for r in policy_rules])
            + f'\n\nتفاصيل فنية: {str(exc)}'
        )


@app.post('/api/ai/assist')
def ai_assist(request: Request, payload: AIAssistPayload):
    user = require_user(request, ['client', 'lawyer', 'admin'])
    _check_rate_limit(f"ai:{user['user_id']}", limit=20, window_s=60)

    policy_rules = _load_ai_policy_rules(payload.policy_rules)
    answer = _generate_ai_text(payload.question, policy_rules)

    if 'ليست استشارة' not in answer:
        answer = f'تنبيه: هذه المعلومات عامة وليست استشارة قانونية نهائية.\n\n{answer}'

    log_action(user['user_id'], 'ai.assist.used', 'ai', None, {'question_length': len(payload.question), 'rules_count': len(policy_rules)})
    return {'success': True, 'data': {'answer': answer, 'policy_rules': policy_rules}}


# =====================================================
# New Page Routes
# =====================================================

@app.get('/cases/new', response_class=HTMLResponse)
def new_case_page(request: Request, lawyer_id: int = None):
    user = require_user(request, ['client', 'admin'])
    lawyer = None
    if lawyer_id:
        with get_conn() as conn:
            lawyer = conn.execute('SELECT * FROM users WHERE id = ? AND user_type = ?', (lawyer_id, 'lawyer')).fetchone()
            if lawyer:
                lawyer = dict(lawyer)
    return _render_with_csrf('case_new.html', request, {'lawyer': lawyer, 'lawyer_id': lawyer_id})


@app.post('/cases/new')
def create_case_form(
    request: Request,
    csrf_token: str = Form(...),
    title: str = Form(...),
    case_type: str = Form(...),
    description: str = Form(...),
    lawyer_id: int = Form(None),
):
    verify_csrf(request, csrf_token)
    user = require_user(request, ['client', 'admin'])
    
    with get_conn() as conn:
        cur = conn.execute(
            'INSERT INTO cases (client_user_id, lawyer_user_id, title, case_type, description, status) VALUES (?, ?, ?, ?, ?, ?)',
            (user['user_id'], lawyer_id, title.strip(), case_type.strip(), description.strip(), 'pending'),
        )
        case_id = cur.lastrowid
    
    log_action(user['user_id'], 'case.created', 'case', case_id)
    return RedirectResponse(f'/cases/{case_id}', status_code=303)


@app.get('/cases/{case_id}', response_class=HTMLResponse)
def case_detail_page(request: Request, case_id: int):
    user = require_user(request, ['client', 'lawyer', 'admin'])
    
    with get_conn() as conn:
        case = conn.execute('SELECT * FROM cases WHERE id = ?', (case_id,)).fetchone()
        if not case:
            raise HTTPException(status_code=404, detail='Case not found')
        
        if user['user_type'] != 'admin' and user['user_id'] not in {case['client_user_id'], case['lawyer_user_id']}:
            raise HTTPException(status_code=403, detail='Forbidden')
        
        client = conn.execute('SELECT * FROM users WHERE id = ?', (case['client_user_id'],)).fetchone()
        lawyer = None
        if case['lawyer_user_id']:
            lawyer = conn.execute('SELECT * FROM users WHERE id = ?', (case['lawyer_user_id'],)).fetchone()
        
        payments = conn.execute('SELECT * FROM payments WHERE case_id = ? ORDER BY id DESC', (case_id,)).fetchall()
        has_payment = len(payments) > 0
    
    return templates.TemplateResponse('case_detail.html', {
        'request': request,
        'user': user,
        'case': dict(case),
        'client': dict(client) if client else None,
        'lawyer': dict(lawyer) if lawyer else None,
        'payments': [dict(p) for p in payments],
        'has_payment': has_payment,
    })


@app.get('/cases/{case_id}/messages', response_class=HTMLResponse)
def case_messages_page(request: Request, case_id: int):
    user = require_user(request, ['client', 'lawyer', 'admin'])
    
    with get_conn() as conn:
        case = conn.execute('SELECT * FROM cases WHERE id = ?', (case_id,)).fetchone()
        if not case:
            raise HTTPException(status_code=404, detail='Case not found')
        
        if user['user_type'] != 'admin' and user['user_id'] not in {case['client_user_id'], case['lawyer_user_id']}:
            raise HTTPException(status_code=403, detail='Forbidden')
        
        messages = conn.execute('SELECT * FROM messages WHERE case_id = ? ORDER BY id ASC', (case_id,)).fetchall()
        
        # Determine other party
        if user['user_id'] == case['client_user_id']:
            other_party_id = case['lawyer_user_id']
        else:
            other_party_id = case['client_user_id']
        
        other_party = None
        if other_party_id:
            other_party = conn.execute('SELECT * FROM users WHERE id = ?', (other_party_id,)).fetchone()
    
    return _render_with_csrf('messages.html', request, {
        'case': dict(case),
        'messages': [dict(m) for m in messages],
        'other_party': dict(other_party) if other_party else None,
        'other_party_id': other_party_id,
        'current_user_id': user['user_id'],
    })


@app.get('/lawyers/{lawyer_id}', response_class=HTMLResponse)
def lawyer_profile_page(request: Request, lawyer_id: int):
    with get_conn() as conn:
        lawyer = conn.execute('SELECT * FROM users WHERE id = ? AND user_type = ?', (lawyer_id, 'lawyer')).fetchone()
        if not lawyer:
            raise HTTPException(status_code=404, detail='Lawyer not found')
        
        lawyer_data = conn.execute('SELECT * FROM lawyers WHERE user_id = ?', (lawyer_id,)).fetchone()
    
    return templates.TemplateResponse('lawyer_profile.html', {
        'request': request,
        'user': current_user(request),
        'lawyer': dict(lawyer),
        'lawyer_data': dict(lawyer_data) if lawyer_data else None,
    })


@app.get('/ai-assistant', response_class=HTMLResponse)
def ai_assistant_page(request: Request):
    user = require_user(request, ['client', 'lawyer', 'admin'])
    return _render_with_csrf('ai_assistant.html', request, {'user': user})


@app.get('/payments', response_class=HTMLResponse)
def payments_page(request: Request):
    user = require_user(request, ['client', 'lawyer', 'admin'])
    
    with get_conn() as conn:
        if user['user_type'] == 'admin':
            payments = conn.execute('SELECT * FROM payments ORDER BY id DESC LIMIT 100').fetchall()
        elif user['user_type'] == 'client':
            payments = conn.execute('SELECT * FROM payments WHERE client_user_id = ? ORDER BY id DESC', (user['user_id'],)).fetchall()
        else:
            payments = conn.execute('SELECT * FROM payments WHERE lawyer_user_id = ? ORDER BY id DESC', (user['user_id'],)).fetchall()
        
        payments_list = [dict(p) for p in payments]
        
        total_pending = sum(1 for p in payments_list if p['status'] == 'pending')
        total_paid = sum(1 for p in payments_list if p['status'] == 'paid')
        total_held = sum(1 for p in payments_list if p['escrow_status'] == 'held')
        total_amount = sum(p['amount'] for p in payments_list)
    
    return templates.TemplateResponse('payments.html', {
        'request': request,
        'user': user,
        'payments': payments_list,
        'total_pending': total_pending,
        'total_paid': total_paid,
        'total_held': total_held,
        'total_amount': total_amount,
    })


@app.get('/profile', response_class=HTMLResponse)
def profile_page(request: Request):
    user = require_user(request, ['client', 'lawyer', 'admin'])
    
    with get_conn() as conn:
        profile = conn.execute('SELECT * FROM users WHERE id = ?', (user['user_id'],)).fetchone()
        
        lawyer_data = None
        if user['user_type'] == 'lawyer':
            lawyer_data = conn.execute('SELECT * FROM lawyers WHERE user_id = ?', (user['user_id'],)).fetchone()
        
        cases_count = conn.execute(
            'SELECT COUNT(*) c FROM cases WHERE client_user_id = ? OR lawyer_user_id = ?',
            (user['user_id'], user['user_id'])
        ).fetchone()['c']
        
        payments_count = conn.execute(
            'SELECT COUNT(*) c FROM payments WHERE client_user_id = ? OR lawyer_user_id = ?',
            (user['user_id'], user['user_id'])
        ).fetchone()['c']
    
    return _render_with_csrf('profile.html', request, {
        'profile': dict(profile),
        'lawyer_data': dict(lawyer_data) if lawyer_data else None,
        'cases_count': cases_count,
        'payments_count': payments_count,
    })


@app.post('/profile/update')
def update_profile(request: Request):
    user = require_user(request, ['client', 'lawyer', 'admin'])
    
    import json as json_lib
    body = json_lib.loads(request._body.decode() if hasattr(request, '_body') else '{}')
    
    with get_conn() as conn:
        # Update user info
        if 'full_name' in body:
            conn.execute('UPDATE users SET full_name = ? WHERE id = ?', (body['full_name'].strip(), user['user_id']))
        
        # Update lawyer info
        if user['user_type'] == 'lawyer':
            updates = []
            params = []
            for field in ['bio', 'governorate', 'city', 'min_consultation_fee']:
                if field in body:
                    updates.append(f'{field} = ?')
                    params.append(body[field])
            
            if updates:
                params.append(user['user_id'])
                conn.execute(f"UPDATE lawyers SET {', '.join(updates)} WHERE user_id = ?", params)
    
    log_action(user['user_id'], 'profile.updated', 'user', user['user_id'])
    return {'success': True, 'message': 'Profile updated'}


@app.get('/admin', response_class=HTMLResponse)
def admin_page(request: Request):
    user = require_user(request, ['admin'])
    
    with get_conn() as conn:
        users = conn.execute('SELECT user_type, COUNT(*) c FROM users GROUP BY user_type').fetchall()
        pending_verifications = conn.execute("SELECT COUNT(*) c FROM lawyer_verification_requests WHERE status IN ('submitted','under_review')").fetchone()['c']
        open_cases = conn.execute("SELECT COUNT(*) c FROM cases WHERE status IN ('pending','accepted','in_progress')").fetchone()['c']
        pending_payments = conn.execute("SELECT COUNT(*) c FROM payments WHERE status IN ('pending','paid') AND escrow_status = 'held'").fetchone()['c']
    
    overview = {
        'users_by_type': {row['user_type']: row['c'] for row in users},
        'pending_verifications': pending_verifications,
        'open_cases': open_cases,
        'pending_payments_in_escrow': pending_payments,
    }
    
    return templates.TemplateResponse('admin.html', {
        'request': request,
        'user': user,
        'active_tab': 'overview',
        'overview': overview,
        'pending_verifications': pending_verifications,
        'verifications': [],
        'cases': [],
        'payments': [],
        'audit_logs': [],
    })


@app.get('/admin/verifications', response_class=HTMLResponse)
def admin_verifications_page(request: Request):
    user = require_user(request, ['admin'])
    
    with get_conn() as conn:
        verifications = conn.execute(
            '''
            SELECT vr.*, u.full_name, u.email
            FROM lawyer_verification_requests vr
            JOIN users u ON u.id = vr.lawyer_user_id
            ORDER BY 
                CASE WHEN vr.status IN ('submitted', 'under_review') THEN 0 ELSE 1 END,
                vr.id DESC
            '''
        ).fetchall()
        pending_verifications = conn.execute("SELECT COUNT(*) c FROM lawyer_verification_requests WHERE status IN ('submitted','under_review')").fetchone()['c']
    
    return templates.TemplateResponse('admin.html', {
        'request': request,
        'user': user,
        'active_tab': 'verifications',
        'overview': {},
        'verifications': [dict(v) for v in verifications],
        'cases': [],
        'payments': [],
        'audit_logs': [],
        'pending_verifications': pending_verifications,
    })


@app.get('/admin/cases', response_class=HTMLResponse)
def admin_cases_page(request: Request):
    user = require_user(request, ['admin'])
    
    with get_conn() as conn:
        cases = conn.execute(
            '''
            SELECT c.*, 
                   client.full_name as client_name,
                   lawyer.full_name as lawyer_name
            FROM cases c
            LEFT JOIN users client ON c.client_user_id = client.id
            LEFT JOIN users lawyer ON c.lawyer_user_id = lawyer.id
            ORDER BY c.id DESC
            LIMIT 100
            '''
        ).fetchall()
        pending_verifications = conn.execute("SELECT COUNT(*) c FROM lawyer_verification_requests WHERE status IN ('submitted','under_review')").fetchone()['c']
    
    return templates.TemplateResponse('admin.html', {
        'request': request,
        'user': user,
        'active_tab': 'cases',
        'overview': {},
        'verifications': [],
        'cases': [dict(c) for c in cases],
        'payments': [],
        'audit_logs': [],
        'pending_verifications': pending_verifications,
    })


@app.get('/admin/payments', response_class=HTMLResponse)
def admin_payments_page(request: Request):
    user = require_user(request, ['admin'])
    
    with get_conn() as conn:
        payments = conn.execute('SELECT * FROM payments ORDER BY id DESC LIMIT 100').fetchall()
        pending_verifications = conn.execute("SELECT COUNT(*) c FROM lawyer_verification_requests WHERE status IN ('submitted','under_review')").fetchone()['c']
    
    return templates.TemplateResponse('admin.html', {
        'request': request,
        'user': user,
        'active_tab': 'payments',
        'overview': {},
        'verifications': [],
        'cases': [],
        'payments': [dict(p) for p in payments],
        'audit_logs': [],
        'pending_verifications': pending_verifications,
    })


@app.get('/admin/audit-logs', response_class=HTMLResponse)
def admin_audit_logs_page(request: Request):
    user = require_user(request, ['admin'])
    
    with get_conn() as conn:
        audit_logs = conn.execute('SELECT * FROM audit_logs ORDER BY id DESC LIMIT 200').fetchall()
        pending_verifications = conn.execute("SELECT COUNT(*) c FROM lawyer_verification_requests WHERE status IN ('submitted','under_review')").fetchone()['c']
    
    return templates.TemplateResponse('admin.html', {
        'request': request,
        'user': user,
        'active_tab': 'audit',
        'overview': {},
        'verifications': [],
        'cases': [],
        'payments': [],
        'audit_logs': [dict(log) for log in audit_logs],
        'pending_verifications': pending_verifications,
    })

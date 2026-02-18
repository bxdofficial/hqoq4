# حقوقي - Python Edition (FastAPI)

نسخة بايثون كاملة من المشروع، جاهزة للتشغيل محليًا والنشر على **PythonAnywhere**، مع تركيز على الامتثال والأمان لسوق مصر.

## Tech Stack
- FastAPI
- Jinja2 Templates
- SQLite
- PBKDF2 Password Hashing + Signed Session Cookies
- Admin Audit Logs + Rule-bound AI Assistant endpoint

## تشغيل محلي
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export APP_SECRET_KEY='replace-with-strong-secret'
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

## متغيرات البيئة
- `APP_SECRET_KEY` **إجباري** (لن يعمل التطبيق بدونه).
- `APP_DB_PATH` اختياري (افتراضي: `hoqouqi.db`).
- `APP_COOKIE_SECURE` (`true` في الإنتاج).
- `GEMINI_API_KEY` اختياري لتشغيل الذكاء الاصطناعي.
- `GEMINI_MODEL` اختياري (افتراضي: `gemini-1.5-flash`).
- `AI_POLICY_RULES` اختياري (سطر لكل قاعدة إضافية ملزمة للرد).

## أهم الصفحات
- `/` الصفحة الرئيسية
- `/register` تسجيل جديد (عميل/محامي)
- `/login` تسجيل الدخول
- `/dashboard` لوحة التحكم
- `/search` بحث المحامين

## أهم واجهات API
- `/api/health` فحص الصحة
- `/api/config/health` فحص الإعدادات (admin)
- `/api/cases` إنشاء/عرض القضايا
- `/api/cases/{case_id}/assign` إسناد محامٍ (admin)
- `/api/cases/{case_id}/status` تحديث حالة القضية
- `/api/payments` إنشاء/عرض المدفوعات
- `/api/payments/{payment_id}/process|release|refund` دورة الدفع (admin)
- `/api/messages` إرسال رسالة ضمن قضية
- `/api/messages/{case_id}` عرض رسائل قضية
- `/api/admin/lawyer-verifications` + `/review` مراجعة توثيق المحامين
- `/api/admin/overview` مؤشرات تشغيلية
- `/api/admin/audit-logs` سجل العمليات الحساسة
- `/api/ai/assist` مساعد AI مقيّد بالسياسات

## النشر على PythonAnywhere
1. ارفع المشروع إلى PythonAnywhere.
2. أنشئ virtualenv وثبّت المتطلبات:
   ```bash
   pip install -r requirements.txt
   ```
3. في إعدادات Web App، اجعل ملف WSGI يشير إلى `wsgi.py`.
4. اضبط متغيرات البيئة أعلاه (خصوصًا `APP_SECRET_KEY`).
5. أعد تحميل التطبيق.

## ملاحظات أمنية
- لا تضع مفاتيح API مباشرة داخل الكود.
- استخدم HTTPS دائمًا.
- تحكم admin مطلوب لكل عمليات حساسة: مراجعة توثيق، إدارة الدفع، وسجلات التدقيق.
- `api/ai/assist` يضيف تنبيه "معلومات عامة وليست استشارة قانونية نهائية" تلقائيًا.

## حالة التنفيذ الحالية
- ✅ Auth + Sessions + CSRF + Rate limiting.
- ✅ Case management أساسي مع صلاحيات واضحة.
- ✅ Payments lifecycle أساسي (pending/paid/released/refunded) بإدارة admin.
- ✅ Messages per case مع تحقق مشاركة الأطراف.
- ✅ Admin overview + audit logs.
- ✅ AI endpoint مقيد باللوائح القابلة للضبط عبر المتغيرات.
- ⚠️ يحتاج لاحقًا تكامل بوابة دفع حقيقية (webhooks) واختبارات آلية CI.

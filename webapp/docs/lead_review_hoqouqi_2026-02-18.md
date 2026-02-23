# Hoqouqi — Lead Review (Product + CTO + Security + Compliance) — Egypt Only

## 0) Executive Summary
- المشروع الحالي **MVP Foundation** جيد تقنياً، لكنه ليس جاهز إطلاق إنتاجي واسع بعد.
- أقوى نقاطه: Authentication أساسي جيد، صلاحيات أدوار معقولة، عمليات Case/Payment/Message أساسية، وسجل تدقيق إداري.
- أكبر فجواته قبل الإطلاق: تكامل دفع حقيقي، اختبارات آلية، مراقبة تشغيل (Observability)، تشديد الحماية المتقدمة (headers/CSRF strategy/API abuse), وامتثال تشغيلي قانوني أكثر تفصيلاً.
- القرار التنفيذي: **استمرار على Python/FastAPI صحيح**، مع خطة 12 أسبوع لإغلاق المخاطر الحرجة والتحويل لإطلاق Pilot منضبط داخل مصر.

---

## A) Audit شامل (تفصيلي)

### 1) Value Proposition
**الحالة:** مفهومة جزئياً: ربط عميل بمحامٍ + إدارة قضايا + مدفوعات + رسائل + AI مساعد سياسات.

**المشكلة:** ما زال هناك اتساع نطاق (AI + عمليات + سوق ثنائي) قد يربك رسالة المنتج.

**التوصية:** صياغة قيمة واحدة للإطلاق:
> "منصة تشغيل قانوني داخل مصر: طلب خدمة قانونية، إسناد لمحامٍ مرخّص، متابعة حالة، ومدفوعات محكومة".

---

### 2) السوق داخل مصر (شرائح + منافسين)
- **شرائح العملاء:** أفراد/SMEs يحتاجون سرعة، وضوح تكلفة، ومحامٍ موثّق.
- **شرائح المحامين:** محامون مستقلون يحتاجون تدفق عملاء، إدارة قضايا، وتحصيل منظم.
- **فجوة رقمية فعلية:** ضعف التشغيل الموحّد (onboarding/assignment/status/payment trail).
- **ملاحظة منهجية:** لا توجد في المشروع بيانات سوق كمية مؤكدة مرفقة؛ القرار يجب أن يبنى على Pilot metrics أولاً.

---

### 3) MVP: ماذا يبنى الآن
**Now (إجباري للإطلاق):**
1. تسجيل/دخول + أدوار.
2. إنشاء قضية + إسناد + تحديث حالة.
3. رسائل مرتبطة بالقضية.
4. مدفوعات أساسية (معالجة/إطلاق/استرداد) مع ضوابط Admin.
5. توثيق محامين + مراجعة Admin.

**Postpone:**
- أي AI قانوني متقدم (توقّع أحكام/صياغة ملزمة).
- Features تسويقية كبيرة بدون أثر مباشر على الإنجاز والإيراد.

---

### 4) UX/UI
**الموجود:** صفحات Home/Login/Register/Dashboard/Search.

**الاحتكاكات:**
- لا يوجد Flow بصري واضح للنزاع أو الاسترداد.
- لا توجد حالات Empty/Failure UX مفصلة.
- لوحة Admin ليست واجهة كاملة؛ غالبًا API-first.

**تحسينات سريعة:**
- Wizard طلب خدمة (4 خطوات).
- صفحة Timeline للقضية (status + messages + payments).
- واجهة Admin تشغيلية فعلية (verification queue/dispute queue).

---

### 5) نموذج الربح (قانوني في مصر)
**مقبول مبدئيًا:** رسوم تقنية/تشغيل + اشتراك محامي اختياري + خدمات مضافة.

**ممنوع/خطر:** تحصيل يبدو كأنه "أتعاب محاماة مباشرة" بدون وضوح العلاقة التعاقدية بين الطرفين.

**توصية:**
- Legal framing واضح: المنصة وسيط تقني وتشغيلي.
- عقود/شروط استخدام تحدد بوضوح العلاقة المالية والمسؤوليات.

---

### 6) العمليات والتشغيل
**الموجود:** verification requests + review + overview + audit logs.

**الناقص:**
- SOPs تشغيل رسمية للنزاعات، SLA موثق، escalation matrix.
- فريق دعم بPlaybooks واضحة.

---

### 7) الثقة (Trust)
**إيجابي:**
- Workflow توثيق محامٍ موجود.
- Audit logging موجود للأحداث الحساسة.

**ناقص:**
- دورة إعادة تحقق دورية للمحامي.
- ضمانات استرداد موثقة للعميل في الواجهة.

---

### 8) الأمن والخصوصية
**إيجابي (مطبق):**
- PBKDF2 hashes.
- Signed session tokens.
- CSRF (form flows).
- Rate limiting أساسي.
- RBAC على endpoints متعددة.

**مخاطر متبقية:**
- Rate limiting in-memory فقط (لا يناسب multi-instance).
- لا توجد security headers middleware موحدة (CSP/HSTS/XFO...).
- لا توجد طبقة logging/monitoring production-grade.

---

### 9) الامتثال داخل مصر
**إيجابي:**
- AI endpoint فيه guardrails وتنبيه "معلومات عامة وليست استشارة نهائية".
- توجيه للمحامي المرخص جزء من السياسة.

**لازم قبل الإطلاق:**
- وثائق Privacy/Terms/Data handling نهائية باللغة العربية القانونية.
- Policy تفصيلية لتجنب "ممارسة قانون بدون ترخيص" على كل touchpoint.

---

### 10) التقنية (Architecture + تكلفة)
- Stack مناسب لـPilot: FastAPI + SQLite + Templates.
- للإطلاق الفعلي: ترقية إلى Postgres + Redis + Object Storage + managed logs.
- تكلفة Pilot منخفضة، لكن قابلية التوسع تتطلب ترقية مكونات التخزين/الحد من الإساءة.

---

### 11) الذكاء الاصطناعي
**ممكن الآن:** FAQ/Guidance عام مقيد بسياسات، routing للمحامي.

**غير ممكن الآن (أو خطر):**
- رأي قانوني نهائي.
- توقع نتيجة قضية.
- توليد مستندات ملزمة دون مراجعة محامٍ.

**بديل عملي:** AI للفرز والتصنيف واستخراج checklist فقط.

---

### 12) قابلية التوسع داخل مصر
- توسع رأسي أولاً: القاهرة/الجيزة/الإسكندرية ثم المحافظات.
- توسع أفقي بعد إثبات economics: شرائح B2B (SMEs) بخطط اشتراك.

---

## B) Findings Lists (قوائم قرار جاهزة)

### 1) Critical Issues (قبل الإطلاق)
1. عدم وجود تكامل بوابة دفع حقيقية (webhooks + reconciliation).
2. عدم وجود اختبارات آلية + CI.
3. عدم وجود Observability production-grade.
4. غياب وثائق امتثال قانونية نهائية (Privacy/Terms/Data processing).
5. Rate limiting موزّع غير متاح (in-memory فقط).

### 2) High Impact Improvements
1. Admin console UI كاملة للتشغيل.
2. Case timeline موحد (status/payment/messages).
3. SLA + dispute workflow رسمي.
4. Postgres + Redis migration plan.
5. Monitoring + alerting + error budgets.

### 3) Nice-to-Have
1. Smart triage غير قانوني (تصنيف نوع الخدمة).
2. NPS/CSAT dashboards.
3. Multi-language UX (AR/EN).

### 4) Remove / Replace / Postpone
- **Remove:** أي claim أن AI يقدّم "استشارة قانونية نهائية".
- **Replace:** SQLite في الإنتاج بـPostgres.
- **Replace:** in-memory rate limit بـRedis-backed.
- **Postpone:** AI document drafting المتقدم.
- **Postpone:** ميزات نمو غير مرتبطة مباشرة بالتحويل/الإيراد.

---

## C) Fix Blueprint (نسخة مشروع 2.0)

### تعريف 2.0
منصة Legal Operations داخل مصر: Intake → Assign → Track → Pay → Resolve.

### MVP النهائي (Feature List دقيقة)
1. Auth + RBAC + Session Security.
2. Client Intake form مضبوط.
3. Case assignment (admin) + case status lifecycle.
4. Case messaging (participant-only).
5. Escrow-like payment states + admin actions.
6. Lawyer verification queue + review decisions.
7. Admin overview + audit logs.

### ما لن يُبنى الآن
- AI legal opinions.
- توقع نتائج القضايا.
- Marketplace معقد بميزات اجتماعية.

### أول 10 قرارات Product يجب حسمها
1. نموذج الربح الأساسي (transaction fee vs subscription mix).
2. سياسة refunds.
3. SLA الأولي لكل نوع خدمة.
4. نطاق المحافظات في Pilot.
5. شروط قبول المحامين.
6. سياسات التعليق/الإيقاف.
7. حدود AI usage.
8. سياسة توثيق الهوية والبيانات.
9. قنوات الدعم الرسمية.
10. معيار الانتقال من Pilot إلى Scale.

---

## D) خطة تنفيذ عملية (12 أسبوع)

### Week 1–2
- تثبيت وثائق الامتثال (Privacy/Terms/Data handling).
- تعريف SOP للنزاعات والدعم.
- إعداد KPI baseline.

### Week 3–4
- تنفيذ Postgres migration plan.
- إدخال Redis rate limiter.
- إضافة security headers middleware.

### Week 5–6
- تكامل دفع فعلي + webhooks.
- reconciliation report يومي.

### Week 7–8
- Admin Ops UI (verification/disputes/audit viewer).
- case timeline UX.

### Week 9–10
- testing suite (unit/integration/e2e) + CI pipeline.
- load/smoke tests.

### Week 11
- Pilot go-live readiness review + incident playbooks.

### Week 12
- إطلاق Pilot مضبوط + post-launch review + backlog reprioritization.

### الفريق الأدنى المطلوب
- Product Manager (part-time)
- 1 Backend Engineer
- 1 Full-stack/Frontend Engineer
- 1 QA (part-time)
- 1 Legal/Compliance Advisor (part-time)
- 1 Ops/Support (part-time at launch)

### KPIs لكل مرحلة
- Time to first response
- Case completion rate
- Payment success rate
- Refund/dispute ratio
- Verification turnaround time
- Weekly active lawyers / active clients

### خطة جذب أول 50 محامي + أول 500 عميل
**50 محامي:**
- شراكات نقابية/مكاتب صغيرة، onboarding يدوي عالي الجودة، عمولة تفضيلية أول 3 أشهر.

**500 عميل:**
- قنوات intent عالية (search + communities + referrals)،
- عروض خدمات محددة التسعير,
- SLA واضح + ضمان refund policy.

---

## E) Documentation Pack (جاهز للنسخ)

### 1) ملخص تنفيذي
حقوقي 2.0 منصة تشغيل قانوني مصرية تركّز على إنجاز الخدمة القانونية، وليس بيع “AI قانوني”.

### 2) افتراضات المشروع
- إطلاق داخل مصر فقط.
- التوسع يبدأ من Pilot جغرافي محدود.
- الامتثال القانوني مقدم على التوسع السريع.

### 3) قرارات تمت الموافقة عليها
- منع AI legal final advice.
- اعتماد محامٍ قبل الاستلام.
- Admin-only للعمليات المالية الحساسة.
- Audit logs إلزامية لكل حدث حساس.

### 4) قائمة المميزات (Now / Next / Later)
**Now:** Auth/RBAC, Cases, Verification, Messages, Payments baseline, Admin overview.

**Next:** Payment gateway real integration, Admin UI كامل, CI/tests, monitoring.

**Later:** Advanced AI triage, B2B bundles, analytics expansion.

### 5) المخاطر وخطة تقليلها
- Risk: ثغرات تشغيل/امتثال → Mitigation: سياسات + تدقيق قانوني + playbooks.
- Risk: فشل مدفوعات → Mitigation: webhook verification + reconciliation.
- Risk: abuse/spam → Mitigation: Redis rate limit + anomaly alerts.

### 6) السياسات المطلوبة
- Privacy Policy (AR)
- Terms of Service (AR)
- Data Handling & Retention Policy
- Dispute & Refund Policy
- Lawyer Verification Policy

### 7) Backlog أولي (P0/P1)
**P0:** دفع حقيقي، CI، مراقبة، توثيق قانوني نهائي.

**P1:** Admin UI, SLA dashboards, scaling infra.

---

## ملحق: تقدير جاهزية الإطلاق
- Pilot Readiness: **7/10** بعد إغلاق P0.
- Scale Readiness: **4.5/10** حالياً قبل P0.


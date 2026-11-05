# HULLOR — Full-stack E-commerce

| অংশ | টেক | কোথায় deploy |
|---|---|---|
| `backend/` | Python · Django · DRF · JWT | **Render** (Blueprint) |
| `frontend/` | Next.js 15 (App Router) | **Vercel** |
| `admin/index.html` | একটাই HTML ফাইল (অ্যাডমিন প্যানেল) | Vercel (frontend এর সাথেই `/admin`) |
| Database + ছবি | Postgres + Storage | **Supabase** |

ফ্লো: Register/Login → Shop → Product → Cart → Checkout → **Cash on Delivery** অর্ডার → অর্ডার ট্র্যাকিং। অনলাইন পেমেন্ট নেই।
কালার থিম পুরনো সাইটের (cream · green · gold)। পুরনো কোনো প্রোডাক্ট রাখা হয়নি — admin panel থেকে নিজের প্রোডাক্ট যোগ করুন।

---
## ১) Supabase সেটআপ (একবার)
1. supabase.com → New project (পাসওয়ার্ড মনে রাখুন)।
2. **Database URL:** Project → *Connect* → **Session pooler** string কপি করুন (Render IPv4 তাই pooler লাগবে):
   `postgresql://postgres.xxxx:[PASSWORD]@aws-0-xx.pooler.supabase.com:5432/postgres` → এটাই `DATABASE_URL`।
3. **ছবির জন্য Storage:** Storage → New bucket → নাম `hullor`, **Public bucket** অন।
   Storage → *S3 Connection* থেকে নিন: Endpoint, Region, এবং **New access key** (Access key ID + Secret)।
   Public domain হবে: `<project-ref>.supabase.co/storage/v1/object/public/hullor`
   (Render free এ ডিস্ক স্থায়ী না, তাই Storage ছাড়া আপলোড করা ছবি হারিয়ে যাবে। চাইলে admin এ শুধু ছবির URL পেস্টও করা যায়।)

## ২) Backend → Render (Blueprint)
1. এই পুরো ফোল্ডার GitHub repo তে push করুন (root এ `render.yaml` থাকবে)।
2. Render → **New → Blueprint** → repo সিলেক্ট → Apply।
3. Dashboard এ যেসব env চাইবে তা দিন:

| Key | মান |
|---|---|
| `DATABASE_URL` | Supabase Session pooler string |
| `CORS_ALLOWED_ORIGINS` | `https://your-site.vercel.app` (কাস্টম ডোমেইন থাকলে সেটাও, কমা দিয়ে) |
| `ADMIN_PHONE` / `ADMIN_PASSWORD` | আপনার admin লগইন (deploy এ অটো তৈরি হয়; পরে পাসওয়ার্ড বদলাতে এখানে বদলে redeploy) |
| `SUPABASE_S3_ENDPOINT` | যেমন `https://xxxx.supabase.co/storage/v1/s3` |
| `SUPABASE_S3_REGION` | যেমন `ap-southeast-1` |
| `SUPABASE_S3_ACCESS_KEY` / `SUPABASE_S3_SECRET_KEY` | S3 access key |
| `SUPABASE_S3_PUBLIC_DOMAIN` | `xxxx.supabase.co/storage/v1/object/public/hullor` |

`SECRET_KEY` অটো তৈরি হয়। Build এ migrate + ক্যাটাগরি seed + admin তৈরি নিজে চলে।
Deploy শেষে `https://hullor-api.onrender.com/api/health/` খুলে `{"status":"ok"}` দেখুন।
> Render free প্লান ১৫ মিনিট idle থাকলে ঘুমিয়ে যায়, প্রথম রিকোয়েস্টে ~৩০–৫০ সেকেন্ড লাগে। সবসময় চালু রাখতে paid প্ল্যান বা UptimeRobot দিয়ে `/api/health/` পিং করুন।

## ৩) Frontend → Vercel
1. Vercel → Add New Project → একই repo → **Root Directory = `frontend`** (Framework: Next.js অটো)।
2. Environment Variables:
   - `NEXT_PUBLIC_API_URL` = `https://hullor-api.onrender.com/api`
   - `NEXT_PUBLIC_SITE_URL` = `https://your-site.vercel.app`
3. Deploy। তারপর Vercel এর URL টা Render এর `CORS_ALLOWED_ORIGINS` এ বসিয়ে Render redeploy করুন।

## ৪) Admin panel
- Vercel এ frontend deploy করলে অ্যাডমিন চলে আসবে **`https://your-site.vercel.app/admin`** এ (`frontend/public/admin/index.html`)।
- লগইন পেজে *API server URL* এ Render URL (`https://hullor-api.onrender.com`) বসান, `ADMIN_PHONE` + `ADMIN_PASSWORD` দিয়ে ঢুকুন। URL ব্রাউজারে সেভ থাকে। চাইলে ফাইলের উপরে `const API_URL` বদলে দিতে পারেন (দুই কপিই — `admin/index.html` ও `frontend/public/admin/index.html`)।
- চাইলে `admin/index.html` আলাদা Vercel/Netlify static সাইট হিসেবেও দেওয়া যায়।
- সেটআপের পর যা করবেন: Settings (ফোন, WhatsApp, ডেলিভারি চার্জ) → Categories (৭টা seed করা আছে) → Products (ভ্যারিয়েন্ট = সাইজ/কালার/স্টক + ছবি) → Banners (চাইলে)।
- Django এর ডিফল্ট admin ব্যাকআপ হিসেবে `/admin/` এ আছে (`https://hullor-api.onrender.com/admin/`)।

## লোকাল চালানো
```bash
cd backend && python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env            # DATABASE_URL খালি = sqlite
python manage.py migrate && python manage.py seed_demo --products   # --products = ছবি ছাড়া ৪টা ডেমো প্রোডাক্ট (ঐচ্ছিক)
python manage.py ensure_admin && python manage.py runserver

cd frontend && cp .env.example .env.local && npm install && npm run dev   # http://localhost:3000
open admin/index.html (বা: cd admin && python -m http.server 8101)
python manage.py test           # ১১টা ব্যাকএন্ড টেস্ট
```

## যা যা আছে
- **কাস্টমার:** রেজিস্টার/লগইন (মোবাইল বা ইমেইল + পাসওয়ার্ড, JWT auto-refresh), প্রোফাইল, সেভড ঠিকানা, উইশলিস্ট, কার্ট (ড্রয়ার + পেজ, সার্ভারে দাম/স্টক যাচাই), কুপন, ৬৪ জেলা সিলেক্ট, COD চেকআউট (লগইন বাধ্যতামূলক), অর্ডার সাকসেস, অর্ডার লিস্ট/ট্র্যাকিং টাইমলাইন, pending অর্ডার নিজে বাতিল, ডেলিভারির পর রিভিউ, সার্চ/ফিল্টার/সর্ট, SEO (metadata, sitemap, robots), মোবাইল রেসপন্সিভ।
- **অ্যাডমিন:** ড্যাশবোর্ড (KPI, ১৪ দিনের সেলস চার্ট), অর্ডার (স্ট্যাটাস, টাইমলাইন, ইনভয়েস প্রিন্ট, CSV), প্রোডাক্ট + ভ্যারিয়েন্ট + ছবি আপলোড, ক্যাটাগরি, ব্যানার, কুপন, কাস্টমার, রিভিউ, সাইট সেটিংস।
- **স্টক:** অর্ডারে অটো কমে; বাতিল/রিটার্নে ফেরত আসে; ওভারসেল ব্লক (transaction lock)। ডেলিভারড হলে COD "paid" হয়।

## জেনে রাখুন
- ডেলিভারি চার্জ ডিফল্ট **০** (পুরনো সাইটের মতো ফ্রি)। Admin → Settings এ ঢাকা/ঢাকার বাইরের চার্জ ও "এত টাকার উপরে ফ্রি" বদলানো যায়।
- "পাসওয়ার্ড ভুলে গেছি" (ইমেইল/SMS) নেই — কাস্টমারের পাসওয়ার্ড লাগলে `/admin/` থেকে রিসেট করুন।
- Vercel build এর সময় backend ঘুমিয়ে থাকলে হোমপেজ প্রথমে ফাঁকা দেখাতে পারে; ~১ মিনিট পর অটো রিফ্রেশ (ISR) হয়ে যায়।

## অর্ডারে OTP (লগইন ছাড়া অর্ডার)
কাস্টমার লগইন ছাড়াই অর্ডার করতে পারে; অর্ডারের আগে মোবাইল নম্বর SMS OTP দিয়ে যাচাই হয় (অ্যাডমিন → Settings → "Checkout OTP" দিয়ে অন/অফ)।

Render → Environment এ দিন:

| Variable | মান |
|---|---|
| `BULKSMSBD_API_KEY` | bulksmsbd.net থেকে পাওয়া API key |
| `BULKSMSBD_SENDER_ID` | Approved Sender ID |
| `OTP_DAILY_LIMIT` (ঐচ্ছিক) | দিনে সর্বোচ্চ OTP সংখ্যা, ডিফল্ট 300 |

- bulksmsbd ড্যাশবোর্ডে **IP whitelist অন রাখবেন না** (Render এর IP বদলায়, নাহলে error `1032`)।
- ব্যালেন্স শেষ হলে (`1007`) কাস্টমার "SMS পাঠানো যাচ্ছে না" দেখবে — Render Logs এ আসল কারণ লেখা থাকে।
- সুরক্ষা: একই নম্বরে ৬০ সেকেন্ডে ১টা, ঘণ্টায় ৫টা; প্রতি কোডে ৫ বার চেষ্টা; একটা কোডে একটাই অর্ডার।

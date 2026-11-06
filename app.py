# app.py - 1/3 - 4 صفحات فقط - PROMAX V2
from flask import Flask, request, jsonify, Response, redirect, make_response
from datetime import datetime, timedelta, timezone
from supabase import create_client, Client
import requests, random, string, json

app = Flask(__name__)

# ===== عدل هنا بس =====
VPS_HOST = "YOUR_VPS_IP"
VPS_TOKEN = "vps_libya_2026_8rT9yU2iO5p"
SUPABASE_URL = "https://xxxx.supabase.co"
SUPABASE_KEY = "حط-مفتاح-supabase-هنا"
ADMIN_KEY = "123456"
ROOT_WALLET = "0x2d447f9d656594f6c65de039aebe7da32a968400"
PORT = 5000
DOMAIN = "yourdomain.com"
# ======================

AGENT_URL = f"http://{VPS_HOST}:5001/api/agent"
ALLOWED_KEYS = [ADMIN_KEY, "123456", "admin123"]
USDT = "0x55d398326f99059fF775485246999027B3196775"
RPC = "https://bsc-dataseed.binance.org/"
TOPIC = "[STRIPPED 66 bytes]"
FILES = ["File.npvt", "File.ssc", "File.nm", "File.hc", "File.ehi", "File.npvs", "File.v2box"]
MADAR_PRICE = 10

try:
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY) if SUPABASE_URL.startswith("http") else None
except Exception as e:
    print("Supabase init:", e)
    supabase = None

@app.errorhandler(Exception)
def _handle_all_errors(e):
    from werkzeug.exceptions import HTTPException
    if isinstance(e, HTTPException):
        if request.path.startswith('/admin') or request.path.startswith('/api') or request.path.startswith('/check'):
            return jsonify({'error': str(e)}), e.code
        return e
    print('SERVER ERROR:', e)
    if request.path.startswith('/admin') or request.path.startswith('/api') or request.path.startswith('/check'):
        return jsonify({'error': str(e)}), 500
    raise e

# ===== VPS CONTROL =====
def agent_create_bundle(user_id, plan):
    try:
        r = requests.post(f"{AGENT_URL}/create_bundle", headers={"X-Agent-Token": VPS_TOKEN}, json={"user_id": user_id, "plan": plan}, timeout=20)
        if r.status_code == 200: return True, r.json()
        return False, r.text
    except Exception as e: return False, str(e)

def agent_delete_bundle(user_id):
    try:
        r = requests.post(f"{AGENT_URL}/delete_bundle", headers={"X-Agent-Token": VPS_TOKEN}, json={"user_id": user_id}, timeout=15)
        return r.status_code == 200
    except: return False

def agent_get_blob(user_id):
    try:
        r = requests.post(f"{AGENT_URL}/get_blob", headers={"X-Agent-Token": VPS_TOKEN}, json={"user_id": user_id}, timeout=15)
        if r.status_code == 200: return r.json().get('blob')
        return None
    except: return None

def agent_status(user_id):
    try:
        r = requests.post(f"{AGENT_URL}/status", headers={"X-Agent-Token": VPS_TOKEN}, json={"user_id": user_id}, timeout=10)
        if r.status_code == 200: return r.json()
        return None
    except: return None

def agent_health():
    try:
        r = requests.get(f"http://{VPS_HOST}:5001/health", timeout=8)
        if r.status_code == 200: return r.json()
        return None
    except: return None

def decode_blob(blob):
    try:
        raw = bytes.fromhex(blob).decode() if isinstance(blob, str) else blob
        return json.loads(raw)
    except: return None

def get_protocols(user_id):
    blob = agent_get_blob(user_id)
    if not blob:
        plan = "paid" if get_active_subscription(user_id) else "free"
        ok, _ = agent_create_bundle(user_id, plan)
        if ok: blob = agent_get_blob(user_id)
    if not blob: return None
    return decode_blob(blob)

# ===== Supabase + تصليح خطأ التاريخ =====
def parse_expire(s):
    if not s: return None
    try:
        # إصلاح خطأ offset-naive vs offset-aware - نحذف +00:00 و Z
        t = str(s).strip()
        if "+" in t: t = t.split("+")[0]
        if "Z" in t: t = t.replace("Z", "")
        t = t.replace("T", " ").split(".")[0][:19]
        return datetime.strptime(t, "%Y-%m-%d %H:%M:%S")
    except: return None

def get_user(user_id):
    if not supabase: return None
    try:
        res = supabase.table("users").select("*").eq("user_id", user_id).execute()
        return res.data[0] if res.data else None
    except: return None

def save_user(user):
    if not supabase: return
    try: supabase.table("users").upsert(user).execute()
    except Exception as e: print("save error", e)

def get_remaining_hours(user):
    if not user or not user.get("expires_at"): return 0
    if user.get("status")=="inactive": return 0
    exp = parse_expire(user["expires_at"])
    if not exp: return 0
    return max(0, (exp - datetime.now()).total_seconds()/3600)

def format_hm(h):
    if h <=0: return "0:00:00"
    total=int(h*3600); hh=total//3600; m=(total%3600)//60; s=total%60
    if hh>=24: d=hh//24; rh=hh%24; return f"{d} يوم {rh}:{m:02d}:{s:02d}"
    return f"{hh}:{m:02d}:{s:02d}"

def get_active_subscription(user_id):
    if not supabase: return None
    try:
        res = supabase.table("subscriptions").select("*").eq("user_id", user_id).eq("is_paid", True).execute()
        if not res.data: return None
        best=None
        for s in res.data:
            exp=parse_expire(s.get("expire_at"))
            if exp and exp>datetime.now():
                if not best or exp>parse_expire(best.get("expire_at")): best=s
        return best
    except: return None

def is_paid_user(uid): return get_active_subscription(uid) is not None

def restore_paid_user(uid):
    sub=get_active_subscription(uid)
    if not sub: return None
    exp=parse_expire(sub.get("expire_at"))
    if not exp: return None
    u={"user_id":uid,"expires_at":exp.strftime("%Y-%m-%d %H:%M:%S"),"status":"active"}
    save_user(u); return u

def get_paid_users_list():
    if not supabase: return []
    try: subs=supabase.table("subscriptions").select("*").eq("is_paid",True).order("expire_at",desc=True).limit(200).execute().data or []
    except: return []
    out=[]; seen=set()
    for s in subs:
        uid=s.get("user_id")
        if not uid or uid in seen: continue
        exp=parse_expire(s.get("expire_at"))
        if not exp: continue
        seen.add(uid)
        tx=s.get("tx_hash") or ""
        is_madar=str(tx).startswith("madar_") or str(tx).startswith("manual_")
        method="مدار" if is_madar else "USDT"
        card_code=""
        if is_madar:
            try:
                used=supabase.table("madar_cards_used").select("*").eq("user_id",uid).execute().data
                if used: card_code=used[-1].get("card_code") or ""
            except: pass
        rem=max(0,(exp-datetime.now()).total_seconds()/3600)
        out.append({"user_id":uid,"method":method,"tx_hash":tx,"card_code":card_code,"amount_paid":s.get("amount_paid") or 0,"expire_at":s.get("expire_at") or "","remaining":rem,"remaining_formatted":format_hm(rem),"is_active":rem>0,"created_at":s.get("created_at") or ""})
    return out

def madar_activate(uid):
    exp=datetime.now()+timedelta(days=30)
    user=get_user(uid) or {"user_id":uid}
    user["expires_at"]=exp.strftime("%Y-%m-%d %H:%M:%S"); user["status"]="active"
    save_user(user)
    try: supabase.table("subscriptions").upsert({"user_id":uid,"expire_at":exp.isoformat(),"is_paid":True,"tx_hash":f"madar_{uid}_{int(datetime.now().timestamp())}","amount_paid":MADAR_PRICE}).execute()
    except: pass
    agent_create_bundle(uid, "paid")
    return True

def amount_for(uid):
    h=abs(hash(str(uid)))%900+100
    return round(1+h/10000,4)

def check_payment(uid):
    amt=amount_for(uid); target=int(amt*10**18)
    try:
        latest=int(requests.post(RPC,json={"jsonrpc":"2.0","method":"eth_blockNumber","params":[],"id":1},timeout=10).json()["result"],16)
        padded="0x000000000000000000000000"+ROOT_WALLET[2:].lower()
        logs=requests.post(RPC,json={"jsonrpc":"2.0","method":"eth_getLogs","params":[{"fromBlock":hex(latest-15000),"toBlock":"latest","address":USDT,"topics":[TOPIC,None,padded]}],"id":1},timeout=15).json().get("result",[])
        used=set()
        try: used={x["tx_hash"] for x in supabase.table("subscriptions").select("tx_hash").execute().data if x.get("tx_hash")}
        except: pass
        for log in logs:
            if int(log["data"],16)>=target and log["transactionHash"] not in used:
                return True, log["transactionHash"], amt
        return False,"no",amt
    except Exception as e: return False,str(e),amt
    # app.py - 2/3 - الصفحات الأربع
# ===== 1. الصفحة الرئيسية =====
HOME_HTML = """<!DOCTYPE html><html dir="rtl" lang="ar"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>PREMIUM GATE</title><script src="https://cdn.tailwindcss.com"></script><style>body{background:#05050f;color:#fff;font-family:system-ui}.glass{background:rgba(255,255,255,.06);border:1px solid rgba(255,255,255,.1);backdrop-filter:blur(10px)}.grad{background:linear-gradient(135deg,#a78bfa,#ec4899);-webkit-background-clip:text;-webkit-text-fill-color:transparent}</style></head><body class="min-h-screen"><div class="max-w-md mx-auto px-4 pb-10"><div class="flex justify-between items-center py-4"><div class="flex items-center gap-2"><div class="w-9 h-9 bg-white rounded-full flex items-center justify-center text-black font-black">P</div><b>PREMIUM GATE</b></div><span class="text-xs text-gray-400" dir="ltr">0x2d44...8400 • SECURE</span></div><div class="text-center mt-2"><span class="glass rounded-full px-4 py-1 text-xs text-emerald-300">● النظام شغال - دخول فوري</span><h1 class="text-4xl font-black leading-tight mt-4">دخولك للمحتوى<br><span class="grad">في ثانية واحدة</span></h1><p class="text-gray-400 text-sm mt-3">رابط واحد ينشئلك حساب، يعطيك ساعتين مجانا، ويفتحلك صفحة العروض الاحترافية.</p><a href="/go" class="block mt-5 bg-white text-black py-4 rounded-2xl font-black text-lg">🚀 إنشاء حساب ودخول فوري</a><div class="grid grid-cols-3 gap-2 mt-4"><div class="glass rounded-2xl p-3 text-center"><p class="text-violet-400 font-black text-xl">2H</p><p class="text-xs text-gray-400">مجانا</p></div><div class="glass rounded-2xl p-3 text-center"><p class="text-emerald-400 font-black text-xl">1$</p><p class="text-xs text-gray-400">30 يوم</p></div><div class="glass rounded-2xl p-3 text-center"><p class="font-black text-xl">∞</p><p class="text-xs text-gray-400">تحميل</p></div></div></div><div class="glass rounded-3xl p-4 mt-5"><div class="flex justify-between items-center"><span class="text-xs text-gray-400">● معاينة حسابك الحقيقي</span><span class="w-2 h-2 bg-emerald-400 rounded-full"></span></div><div class="bg-black/40 rounded-2xl p-4 mt-3"><div class="flex items-center gap-2"><span>👤</span><b id="myid">user_------</b></div><p class="text-sm mt-2 text-gray-300">متبقي: <span id="mytime" class="text-emerald-400 font-bold">--:--:--</span> : متبقي &nbsp; حالة: <span id="mystatus">...</span></p><div class="grid grid-cols-2 gap-2 mt-3"><a id="mylib" href="#" class="bg-violet-500 py-2.5 rounded-xl text-center font-bold text-sm">📁 محتوى</a><a id="mypay" href="#" class="bg-emerald-500 text-black py-2.5 rounded-xl text-center font-bold text-sm">💳 دفع</a></div></div></div><div class="fixed bottom-4 right-4 w-12 h-12 bg-white text-black rounded-full flex items-center justify-center text-xl shadow-xl cursor-pointer" onclick="alert('الدعم: راسلنا على التليجرام')">💬</div></div><script>let uid=localStorage.getItem('last_uid')||document.cookie.match(/last_user_id=([^;]+)/)?.[1];if(uid){document.getElementById('myid').innerText=uid;document.getElementById('mylib').href='/view/'+uid;document.getElementById('mypay').href='/pay/'+uid;fetch('/check?user_id='+uid).then(r=>r.json()).then(d=>{document.getElementById('mytime').innerText=d.hours||'0:00:00';document.getElementById('mystatus').innerText=d.status||'';});}else{document.getElementById('mystatus').innerText='مافيش حساب - أنشئ واحد';}</script></body></html>"""

# ===== 2. صفحة الدفع - USDT + مدار =====
PAY_HTML = """<!DOCTYPE html><html dir="rtl" lang="ar"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>الدفع</title><script src="https://cdn.tailwindcss.com"></script><style>body{background:#05050f;color:#fff}.glass{background:rgba(255,255,255,.06);border:1px solid rgba(255,255,255,.1)}</style></head><body class="min-h-screen"><div class="max-w-md mx-auto px-4 pt-6 pb-10"><a href="/" class="text-sm text-gray-400">← رجوع</a><div id="usdtBox" class="glass rounded-3xl p-5 mt-4"><h1 class="text-xl font-black text-center">الدفع الآمن - USDT (BEP20)</h1><div class="bg-black/40 rounded-2xl p-4 mt-4 flex justify-between items-center"><span class="text-emerald-400 font-black text-xl">USDT <span id="amt">...</span></span><button onclick="copyAmt()" class="bg-white/10 px-3 py-1.5 rounded-lg text-xs">📋 نسخ المبلغ</button></div><div class="bg-black/40 rounded-2xl p-4 mt-3"><p class="text-xs text-gray-400 text-left">عنوان المحفظة</p><p class="text-sm break-all mt-1" dir="ltr" id="wallet">__WALLET__</p><button onclick="copyWallet()" class="bg-white/10 px-3 py-1.5 rounded-lg text-xs mt-2">📋 نسخ المحفظة</button></div><button id="vbtn" class="w-full mt-4 bg-emerald-400 text-black py-3.5 rounded-2xl font-black">لقد دفعت، فعل حسابي</button><button onclick="showMadar()" class="w-full mt-3 bg-yellow-400 text-black py-3.5 rounded-2xl font-black">💳 الدفع بالمدار - 10 دينار</button><p class="text-center text-xs text-gray-500 mt-3">عرض المحتوى</p></div><div id="madarBox" class="glass rounded-3xl p-5 mt-4 hidden"><h1 class="text-xl font-black text-center">دفع بالمدار - 10 دينار</h1><p class="text-center text-xs text-yellow-300 mt-1">سيتم مراجعته يدويا وتفعيل حسابك</p><input id="card" placeholder="رقم الكرت السري" class="w-full mt-4 bg-black border border-white/20 rounded-2xl px-4 py-4 text-center text-white placeholder-gray-500"><button onclick="sendMadar()" class="w-full mt-3 bg-yellow-400 text-black py-4 rounded-2xl font-black">ارسال الكرت للمراجعة</button><p id="madarMsg" class="text-center text-sm mt-3"></p><button onclick="showUsdt()" class="w-full mt-2 text-xs text-gray-400">← رجوع لـ USDT</button></div></div><script>const UID="__UID__";const WALLET="__WALLET__";let AMT="";fetch('/amount/'+UID).then(r=>r.json()).then(d=>{AMT=d.amount;document.getElementById('amt').innerText=d.amount;});function copyAmt(){navigator.clipboard.writeText(AMT);alert('تم نسخ المبلغ');}function copyWallet(){navigator.clipboard.writeText(WALLET);alert('تم نسخ المحفظة');}document.getElementById('vbtn').onclick=async()=>{let r=await fetch('/verify/'+UID).then(r=>r.json());if(r.paid){alert('تم التفعيل 30 يوم ✅');location.href='/view/'+UID;}else alert('لم نجد الدفع بعد، تأكد أنك أرسلت المبلغ بالضبط');};function showMadar(){document.getElementById('usdtBox').classList.add('hidden');document.getElementById('madarBox').classList.remove('hidden');}function showUsdt(){document.getElementById('madarBox').classList.add('hidden');document.getElementById('usdtBox').classList.remove('hidden');}async function sendMadar(){let c=document.getElementById('card').value.trim();if(!c){alert('اكتب رقم الكرت');return;}let r=await fetch('/api/madar/charge-card',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({user_id:UID,card_code:c})}).then(r=>r.json());if(r.status=='pending') document.getElementById('madarMsg').innerText='✅ تم ارسال الكرت، انتظر تفعيل الأدمن';else if(r.status=='used') document.getElementById('madarMsg').innerText='❌ الكرت مستعمل من قبل';else document.getElementById('madarMsg').innerText='❌ خطأ، حاول تاني';}</script></body></html>"""

# ===== 3. صفحة المكتبة =====
LIBRARY_HTML = """<!DOCTYPE html><html dir="rtl" lang="ar"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>مكتبتك</title><script src="https://cdn.tailwindcss.com"></script><style>body{background:#05050f;color:#fff}.glass{background:rgba(255,255,255,.06);border:1px solid rgba(255,255,255,.1)}.grad{background:linear-gradient(135deg,#a78bfa,#ec4899);-webkit-background-clip:text;-webkit-text-fill-color:transparent}.ring{width:150px;height:150px;border-radius:50%;background:conic-gradient(#a78bfa,#10b981,#a78bfa);display:flex;align-items:center;justify-content:center}.ring-in{width:130px;height:130px;border-radius:50%;background:#0a0a1a;display:flex;flex-direction:column;align-items:center;justify-content:center}</style></head><body class="min-h-screen"><div class="max-w-md mx-auto px-4 pb-10"><div class="flex justify-between items-center py-4"><div class="flex items-center gap-2"><div class="w-9 h-9 bg-white rounded-full flex items-center justify-center text-black font-black">P</div><b>PREMIUM GATE</b></div><div class="flex gap-2"><a href="/" class="glass px-3 py-1.5 rounded-full text-xs">🏠 الرئيسية</a><span class="glass px-3 py-1.5 rounded-full text-xs">👤 حسابي</span></div></div><div class="text-center mt-1"><span class="glass rounded-full px-3 py-1 text-xs text-emerald-300">● مكتبتك مفتوحة</span> <span class="glass rounded-full px-3 py-1 text-xs">⭐ PRO</span><h1 class="text-3xl font-black leading-tight mt-3">مكتبتك الخاصة<br><span class="grad">كل ملفاتك في مكان واحد</span></h1><p class="text-gray-400 text-sm mt-2">حمّل أي ملف بضغطة واحدة. ملفاتك محمية بحسابك ومربوطة بوقتك المتبقي.</p></div><div class="flex gap-2 mt-4"><div class="glass rounded-2xl px-4 py-2.5 flex-1 flex justify-between"><span class="text-gray-400 text-sm">📁 الملفات</span><b>7 ملف</b></div><div class="glass rounded-2xl px-4 py-2.5 flex-1 flex justify-between"><span class="text-gray-400 text-sm">👤 ID</span><b>__UID__</b></div></div><div class="flex justify-end mt-2"><span class="glass rounded-full px-3 py-1 text-xs">🛡 حماية: <b class="text-emerald-400">نشطة</b></span></div><div class="glass rounded-3xl p-5 mt-4 flex flex-col items-center"><div class="ring"><div class="ring-in"><span class="text-xs text-gray-400">متبقي</span><b class="text-xl" id="time">--:--:--</b><span class="text-emerald-400 text-xs font-bold" id="status">نشط</span></div></div><div class="flex gap-2 mt-4"><a href="/pay/__UID__" class="bg-emerald-400 text-black px-5 py-2.5 rounded-xl font-bold text-sm">💳 تجديد</a><button onclick="loadProto()" class="glass px-5 py-2.5 rounded-xl font-bold text-sm">حسابي</button></div><div class="w-full mt-4"><div class="flex justify-between text-xs text-gray-400"><span>نسبة الوقت المستهلك</span><span id="pct">0% مستهلك</span></div><div class="h-2 bg-white/10 rounded-full mt-1 overflow-hidden"><div id="bar" class="h-full bg-gradient-to-r from-violet-500 to-emerald-400" style="width:0%"></div></div></div></div><div id="proto" class="mt-4 space-y-2"></div><div class="glass rounded-2xl px-4 py-3 mt-4 flex gap-2"><span>🔍</span><input id="search" oninput="filterFiles()" placeholder="دوّر على ملف... مثل File.ehi" class="bg-transparent flex-1 outline-none text-sm placeholder-gray-500"></div><div class="flex gap-2 mt-3 overflow-x-auto pb-1"><button onclick="setFilter('all')" class="bg-white text-black px-4 py-1.5 rounded-full text-xs font-bold whitespace-nowrap">الكل</button><button onclick="setFilter('vpn')" class="glass px-4 py-1.5 rounded-full text-xs whitespace-nowrap">VPN</button><button onclick="setFilter('config')" class="glass px-4 py-1.5 rounded-full text-xs whitespace-nowrap">Configs</button><button onclick="setFilter('other')" class="glass px-4 py-1.5 rounded-full text-xs whitespace-nowrap">أخرى</button></div><div id="list" class="grid grid-cols-2 gap-2 mt-3"></div></div><script>const UID="__UID__";let FILTER='all';async function load(){let c=await fetch('/check?user_id='+UID).then(r=>r.json());document.getElementById('time').innerText=c.hours||'0:00:00';document.getElementById('status').innerText=c.status=='cooldown'?'انتهى':c.status=='disabled'?'معطل':'نشط';let h="";(c.files||[]).forEach(f=>{h+='<div class="glass rounded-2xl p-4 file-card" data-name="'+f+'"><p class="font-bold text-sm" dir="ltr">'+f+'</p><p class="text-xs text-gray-400 mt-1">ملف جاهز • VPS</p><a href="/download/'+f+'?user_id='+UID+'" class="block text-center mt-3 bg-white text-black py-2 rounded-xl font-bold text-xs">⬇ تحميل</a></div>';});document.getElementById('list').innerHTML=h;}async function loadProto(){let p=await fetch('/api/protocols/'+UID).then(r=>r.json()).catch(()=>null);let box=document.getElementById('proto');if(!p||!p.ok){box.innerHTML='<div class="glass rounded-2xl p-3 text-sm text-center">VPS غير متصل حاليا</div>';return;}let cfg=p.config;let html='<div class="glass rounded-3xl p-4"><b>🔐 بروتوكولاتك - انسخ اللي تبيه</b>';function card(t,v){return '<div class="bg-black/40 rounded-xl p-3 mt-2"><div class="flex justify-between"><b class="text-sm">'+t+'</b><button onclick="navigator.clipboard.writeText(`'+v.replace(/`/g,'')+'`);alert(\\'تم النسخ\\')" class="bg-white text-black px-2 py-1 rounded-lg text-xs font-bold">نسخ</button></div><p class="text-xs break-all mt-1 text-gray-300" dir="ltr">'+v+'</p></div>';}if(cfg.ssh) html+=card('SSH',cfg.ssh.username+':'+cfg.ssh.password+'@'+cfg.ssh.host+':'+cfg.ssh.port);if(cfg.tls) html+=card('TLS',cfg.tls.host+':'+cfg.tls.port+' SNI:'+cfg.tls.sni);if(cfg.vless) html+=card('VLESS',cfg.vless.link);if(cfg.trojan) html+=card('Trojan',cfg.trojan.link);if(cfg.vmess) html+=card('VMESS',cfg.vmess.link);html+='</div>';box.innerHTML=html;}function setFilter(f){FILTER=f;filterFiles();}function filterFiles(){let q=(document.getElementById('search').value||'').toLowerCase();document.querySelectorAll('.file-card').forEach(el=>{let n=el.dataset.name.toLowerCase();let show=n.includes(q);if(FILTER=='vpn') show=show&&(n.includes('npv')||n.includes('ehi')||n.includes('hc'));if(FILTER=='config') show=show&&(n.includes('ssc')||n.includes('nm'));el.style.display=show?'block':'none';});}load();loadProto();</script></body></html>"""

# ===== 4. صفحة الأدمن - PROMAX V2 =====
ADMIN_HTML = """<!DOCTYPE html><html dir="rtl" lang="ar"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>PROMAX V2 - Admin</title><script src="https://cdn.tailwindcss.com"></script><style>body{background:#05050f;color:#fff}.glass{background:rgba(255,255,255,.06);border:1px solid rgba(255,255,255,.1)}</style></head><body class="min-h-screen"><div class="max-w-3xl mx-auto px-4 pb-10"><div class="flex justify-between items-center py-4 flex-wrap gap-2"><b class="text-xl">PROMAX V2 - يدوي</b><div class="flex gap-2"><span class="bg-emerald-500/20 text-emerald-300 px-3 py-1 rounded-full text-xs">key: 123456</span><input id="searchUser" placeholder="بحث user_id" class="bg-white/10 rounded-full px-3 py-1 text-xs outline-none w-32"></div></div><div class="grid grid-cols-5 gap-2 text-center"><div class="glass rounded-2xl p-3"><p class="text-xs text-gray-400">مجاني</p><b class="text-lg" id="cFree">--</b></div><div class="glass rounded-2xl p-3"><p class="text-xs text-gray-400">نشط مجاني</p><b class="text-lg text-emerald-400" id="cActive">--</b></div><div class="glass rounded-2xl p-3"><p class="text-xs text-gray-400">منتهي</p><b class="text-lg text-red-400" id="cExpired">--</b></div><div class="glass rounded-2xl p-3"><p class="text-xs text-gray-400">مدفوع</p><b class="text-lg" id="cPaid">--</b></div><div class="glass rounded-2xl p-3"><p class="text-xs text-gray-400">أجهزة</p><b class="text-lg" id="cDev">--</b></div></div><div class="flex gap-2 mt-4 overflow-x-auto pb-1"><button onclick="showTab('madar')" id="tab-madar" class="glass px-4 py-2 rounded-full text-sm whitespace-nowrap">💳 كروت المدار</button><button onclick="showTab('usdt')" id="tab-usdt" class="glass px-4 py-2 rounded-full text-sm whitespace-nowrap">💵 USDT</button><button onclick="showTab('paid')" id="tab-paid" class="bg-violet-500 px-4 py-2 rounded-full text-sm whitespace-nowrap font-bold">⭐ المشتركين</button><button onclick="showTab('users')" id="tab-users" class="glass px-4 py-2 rounded-full text-sm whitespace-nowrap">👥 المستخدمين</button><button onclick="showTab('vps')" id="tab-vps" class="glass px-4 py-2 rounded-full text-sm whitespace-nowrap">🖥️ VPS</button></div><div class="glass rounded-3xl p-4 mt-3"><div class="flex justify-between items-center flex-wrap gap-2"><b id="boxTitle">⭐ المشتركين المدفوعين - مدار + USDT</b><button onclick="refreshAll()" class="bg-white text-black px-3 py-1.5 rounded-full text-xs font-bold">تحديث</button></div><div id="paidFilter" class="flex gap-2 mt-3"><button onclick="setPaidFilter('all')" class="bg-white text-black px-3 py-1.5 rounded-full text-xs font-bold">الكل</button><button onclick="setPaidFilter('madar')" class="bg-yellow-400 text-black px-3 py-1.5 rounded-full text-xs font-bold">مدار فقط</button><button onclick="setPaidFilter('usdt')" class="bg-emerald-400 text-black px-3 py-1.5 rounded-full text-xs font-bold">USDT فقط</button></div><div id="box" class="mt-3 space-y-2"></div></div></div><script>const KEY=new URLSearchParams(location.search).get("key")||"123456";let PAID_FILTER='all';let PAID_DATA=[];async function refreshAll(){let [users,paid,dev]=await Promise.all([fetch('/admin/users?key='+KEY).then(r=>r.json()).catch(()=>[]),fetch('/admin/paid?key='+KEY).then(r=>r.json()).catch(()=>[]),fetch('/admin/devices?key='+KEY).then(r=>r.json()).catch(()=>[])]);PAID_DATA=paid;let active=users.filter(u=>u.is_active).length;let expired=users.filter(u=>!u.is_active).length;document.getElementById('cFree').innerText=users.length;document.getElementById('cActive').innerText=active;document.getElementById('cExpired').innerText=expired;document.getElementById('cPaid').innerText=paid.length;document.getElementById('cDev').innerText=dev.length;showTab(currentTab);}let currentTab='paid';function setPaidFilter(f){PAID_FILTER=f;showTab('paid');}async function showTab(t){currentTab=t;document.querySelectorAll('[id^="tab-"]').forEach(b=>b.classList.remove('bg-violet-500'));let tb=document.getElementById('tab-'+t);if(tb) tb.classList.add('bg-violet-500');let box=document.getElementById('box');box.innerHTML='جاري التحميل...';let pf=document.getElementById('paidFilter');pf.style.display=t=='paid'?'flex':'none';document.getElementById('boxTitle').innerText=t=='madar'?'💳 كروت المدار - بانتظار المراجعة':t=='usdt'?'💵 مدفوعين USDT':t=='paid'?'⭐ المشتركين المدفوعين - مدار + USDT':t=='vps'?'🖥️ كنترول VPS': '👥 المستخدمين (مجاني)';if(t=='paid'){let list=PAID_DATA.filter(x=>PAID_FILTER=='all'||x.method.toLowerCase().includes(PAID_FILTER=='madar'?'مدار':'USDT')||(PAID_FILTER=='madar'&&x.method=='مدار')||(PAID_FILTER=='usdt'&&x.method=='USDT'));if(PAID_FILTER=='madar') list=PAID_DATA.filter(x=>x.method=='مدار');if(PAID_FILTER=='usdt') list=PAID_DATA.filter(x=>x.method=='USDT');let h='';list.forEach(x=>{h+='<div class="bg-black/30 rounded-2xl p-3 flex justify-between items-center flex-wrap gap-2"><div><b>'+x.user_id+'</b><p class="text-xs text-gray-400">'+x.method+' • '+(x.card_code||x.tx_hash||'').slice(0,20)+' • متبقي '+x.remaining_formatted+'</p></div><div class="flex gap-1"><button onclick="extendPaid(\\''+x.user_id+'\\')" class="bg-emerald-500 text-black px-2 py-1 rounded-lg text-xs font-bold">+30 يوم</button><button onclick="viewProto(\\''+x.user_id+'\\')" class="bg-violet-500 px-2 py-1 rounded-lg text-xs">بروتوكولات</button></div></div>';});box.innerHTML=h||'فارغ';return;}let url=t=='madar'?'/admin/madar-pending?key='+KEY:t=='usdt'?'/admin/usdt?key='+KEY:t=='vps'?'/admin/vps/users?key='+KEY:'/admin/users?key='+KEY;let d=await fetch(url).then(r=>r.json()).catch(()=>[]);let h='';if(t=='madar'){d.forEach(x=>{h+='<div class="bg-black/30 rounded-2xl p-3 flex justify-between"><div><b>'+x.user_id+'</b><p class="text-xs text-gray-400">'+(x.card_code||'')+' - '+x.status+'</p></div>'+(x.status=='pending'?'<div class="flex gap-1"><button onclick="approveMadar('+x.id+',\\''+x.user_id+'\\',\\''+(x.card_code||'')+'\\')" class="bg-emerald-500 text-black px-2 py-1 rounded-lg text-xs font-bold">✅ تفعيل</button><button onclick="rejectMadar('+x.id+')" class="bg-red-500 px-2 py-1 rounded-lg text-xs">❌ رفض</button></div>':'')+'</div>';});}else if(t=='usdt'){d.forEach(x=>{h+='<div class="bg-black/30 rounded-2xl p-3 flex justify-between"><div><b>'+x.user_id+'</b><p class="text-xs text-gray-400">'+x.tx_hash+' • '+x.remaining_formatted+'</p></div><button onclick="extendPaid(\\''+x.user_id+'\\')" class="bg-emerald-500 text-black px-2 py-1 rounded-lg text-xs">+30</button></div>';});}else if(t=='vps'){d.forEach(x=>{h+='<div class="bg-black/30 rounded-2xl p-3 flex justify-between flex-wrap gap-2"><div><b>'+x.user_id+'</b><p class="text-xs text-gray-400">VPS: '+(x.vps?.exists?'✅ '+(x.vps.plan||''):'❌ مافيش')+' | '+x.remaining_formatted+'</p></div><div class="flex gap-1"><button onclick="vpsUser(\\''+x.user_id+'\\',\\'free\\')" class="bg-blue-500 px-2 py-1 rounded-lg text-xs">Free</button><button onclick="vpsUser(\\''+x.user_id+'\\',\\'paid\\')" class="bg-emerald-500 text-black px-2 py-1 rounded-lg text-xs">Paid</button><button onclick="vpsUser(\\''+x.user_id+'\\',\\'delete\\')" class="bg-red-500 px-2 py-1 rounded-lg text-xs">حذف VPS</button></div></div>';});}else{d.forEach(x=>{h+='<div class="bg-black/30 rounded-2xl p-3 flex justify-between"><div><b>'+x.user_id+'</b><p class="text-xs text-gray-400">'+x.remaining_formatted+' • '+(x.is_active?'نشط':'منتهي')+'</p></div><button onclick="delUser(\\''+x.user_id+'\\')" class="bg-red-500 px-2 py-1 rounded-lg text-xs">حذف</button></div>';});}box.innerHTML=h||'فارغ';}async function vpsUser(uid,act){let url=act=='delete'?'/admin/vps/delete?key='+KEY:'/admin/vps/create?key='+KEY;let body=act=='delete'?{user_id:uid}:{user_id:uid,plan:act};let r=await fetch(url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}).then(r=>r.json());alert(r.message||JSON.stringify(r));refreshAll();}async function viewProto(uid){let r=await fetch('/api/protocols/'+uid).then(r=>r.json());alert(JSON.stringify(r.config||r,null,2).slice(0,2000));}async function approveMadar(id,uid,card){if(!confirm('هل شحنت '+card+' ؟'))return;let r=await fetch('/admin/madar-approve?key='+KEY,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id:id,user_id:uid,card_code:card})}).then(r=>r.json());alert(r.message||'تم');refreshAll();}async function rejectMadar(id){await fetch('/admin/madar-reject?key='+KEY,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id:id})});refreshAll();}async function extendPaid(uid){let r=await fetch('/admin/paid-extend?key='+KEY,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({user_id:uid})}).then(r=>r.json());alert(r.message||'تم');refreshAll();}async function delUser(uid){if(!confirm('حذف '+uid+' ؟'))return;await fetch('/admin/action?key='+KEY,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({user_id:uid,action:'delete'})});refreshAll();}refreshAll();</script></body></html>"""
# app.py - 3/3 - نهاية الملف
@app.route('/')
def home(): return Response(HOME_HTML, mimetype='text/html')

@app.route('/health')
def health():
    st = agent_status("test_health") if VPS_HOST != "YOUR_VPS_IP" else None
    return jsonify({"ok": True, "vps_host": VPS_HOST, "agent_reachable": st is not None or agent_health() is not None, "agent_health": agent_health(), "supabase": bool(supabase)})

@app.route('/go')
def go():
    ip = request.headers.get('X-Forwarded-For', request.remote_addr).split(',')[0].strip()
    fp = request.args.get('fp','').strip() or request.cookies.get('device_fp','').strip()
    if fp and fp.startswith('fp_') and supabase:
        try:
            res = supabase.table("device_limits").select("*").eq("fingerprint", fp).execute()
            if res.data:
                row=res.data[0]
                created=parse_expire(row.get("created_at",""))
                if created and (datetime.now()-created).total_seconds()/3600 < 24:
                    return redirect(f"/view/{row['user_id']}")
        except: pass
    uid='user_'+''.join(random.choices(string.digits,k=6))
    exp=datetime.now()+timedelta(hours=2)
    user={"user_id":uid,"expires_at":exp.strftime("%Y-%m-%d %H:%M:%S"),"status":"active","ip_address":ip}
    save_user(user)
    if fp and fp.startswith('fp_') and supabase:
        try: supabase.table("device_limits").upsert({"fingerprint":fp,"user_id":uid,"ip_address":ip,"created_at":datetime.now().isoformat()},on_conflict="fingerprint").execute()
        except: pass
    ok,res=agent_create_bundle(uid,"free")
    if not ok: print(f"VPS FAIL free {uid}: {res}")
    resp=redirect(f"/view/{uid}")
    if fp: resp.set_cookie('device_fp',fp,max_age=86400*30,samesite='Lax')
    resp.set_cookie('last_user_id',uid,max_age=86400,samesite='Lax')
    return resp

@app.route('/clear')
def clear():
    resp=make_response("<script>localStorage.clear(); alert('تم المسح'); window.location='/';</script>")
    resp.set_cookie('device_fp','',expires=0); resp.set_cookie('last_user_id','',expires=0)
    return resp

@app.route('/view/<user_id>')
def view_user(user_id):
    u=get_user(user_id)
    if not u:
        restored=restore_paid_user(user_id)
        if restored: u=restored
        else:
            exp=datetime.now()+timedelta(hours=2)
            u={"user_id":user_id,"expires_at":exp.strftime("%Y-%m-%d %H:%M:%S"),"status":"active"}
            save_user(u)
    else:
        sub=get_active_subscription(user_id)
        if sub:
            exp=parse_expire(sub.get("expire_at"))
            if exp and exp>datetime.now() and parse_expire(u.get("expires_at"))!=exp:
                u["expires_at"]=exp.strftime("%Y-%m-%d %H:%M:%S"); u["status"]="active"; save_user(u)
    return Response(LIBRARY_HTML.replace("__UID__", user_id),mimetype='text/html')

@app.route('/pay/<user_id>')
def pay_page(user_id): return Response(PAY_HTML.replace("__WALLET__",ROOT_WALLET).replace("__UID__",user_id),mimetype='text/html')
@app.route('/content/<user_id>')
def content_page(user_id): return Response(LIBRARY_HTML.replace("__UID__",user_id),mimetype='text/html')
@app.route('/pay-madar/<user_id>')
def pay_madar_page(user_id): return Response(PAY_HTML.replace("__WALLET__",ROOT_WALLET).replace("__UID__",user_id),mimetype='text/html')
@app.route('/amount/<user_id>')
def amount_api(user_id): return jsonify({"amount":amount_for(user_id),"wallet":ROOT_WALLET})

@app.route('/api/support/send', methods=['POST'])
def support_send():
    data=request.get_json(silent=True) or {}
    try: supabase.table("support_messages").insert({"user_id":data.get("user_id","guest"),"message":data.get("message"),"sender":data.get("sender","user")}).execute()
    except Exception as e: return jsonify({"ok":False,"error":str(e)}),500
    return jsonify({"ok":True})

@app.route('/api/support/get')
def support_get():
    uid=request.args.get("user_id","guest")
    try:
        res=supabase.table("support_messages").select("*").eq("user_id",uid).order("created_at").limit(50).execute()
        return jsonify(res.data or [])
    except: return jsonify([])

@app.route('/verify/<user_id>')
def verify_api(user_id):
    ok,tx,amt=check_payment(user_id)
    if ok:
        exp=datetime.now()+timedelta(days=30)
        user=get_user(user_id) or {"user_id":user_id}
        user["expires_at"]=exp.strftime("%Y-%m-%d %H:%M:%S"); user["status"]="active"; save_user(user)
        try: supabase.table("subscriptions").upsert({"user_id":user_id,"expire_at":exp.isoformat(),"is_paid":True,"tx_hash":tx,"amount_paid":amt}).execute()
        except: pass
        agent_create_bundle(user_id,"paid")
        return jsonify({"paid":True})
    return jsonify({"paid":False,"amount":amt})

@app.route('/check', methods=['GET'])
def check():
    user_id=request.args.get('user_id')
    if not user_id: return jsonify({"error":"user_id missing"}),400
    now=datetime.now(); user=get_user(user_id)
    base_url=request.host_url
    links=[f"{base_url}download/{f}?user_id={user_id}" for f in FILES]
    vps = agent_status(user_id)
    vps_txt = "VPS ✅" if vps and vps.get("exists") else "VPS ❌"
    if not user:
        restored=restore_paid_user(user_id)
        if restored: return jsonify({"status":"active","links":links,"files":FILES,"hours":format_hm(get_remaining_hours(restored)),"vps_status":vps_txt})
        expires=now+timedelta(hours=2)
        user={"user_id":user_id,"expires_at":expires.strftime("%Y-%m-%d %H:%M:%S"),"status":"active"}
        save_user(user); agent_create_bundle(user_id,"free")
        return jsonify({"status":"active","links":links,"files":FILES,"hours":"2:00:00","vps_status":vps_txt})
    sub=get_active_subscription(user_id)
    if sub:
        exp=parse_expire(sub.get("expire_at"))
        if exp and exp>now:
            user["expires_at"]=exp.strftime("%Y-%m-%d %H:%M:%S"); user["status"]="active"; save_user(user)
            return jsonify({"status":"active","links":links,"files":FILES,"hours":format_hm(get_remaining_hours(user)),"vps_status":vps_txt})
    if user.get("status")=="inactive": return jsonify({"status":"disabled","message":"تم تعطيل حسابك","hours":"معطل","files":FILES,"vps_status":vps_txt})
    remaining=get_remaining_hours(user)
    if remaining<=0:
        last=parse_expire(user["expires_at"]) or now
        since=(now-last).total_seconds()/3600
        if since>=24:
            new=now+timedelta(hours=2)
            user["expires_at"]=new.strftime("%Y-%m-%d %H:%M:%S"); user["status"]="active"; save_user(user); agent_create_bundle(user_id,"free")
            return jsonify({"status":"active","links":links,"files":FILES,"hours":"2:00:00","vps_status":vps_txt})
        else: return jsonify({"status":"cooldown","message":f"انتهى - انتظر {format_hm(24-since)}","hours":format_hm(24-since),"files":FILES,"vps_status":vps_txt})
    return jsonify({"status":"active","links":links,"files":FILES,"hours":format_hm(remaining),"vps_status":vps_txt})

@app.route('/download/<filename>')
def download(filename):
    user_id=request.args.get('user_id')
    if not user_id: return "user_id missing",400
    user=get_user(user_id)
    if not user:
        restored=restore_paid_user(user_id)
        if restored: user=restored
        else: return redirect(f"/pay/{user_id}")
    if user.get("status")=="inactive": return Response("معطل",403)
    if get_remaining_hours(user)<=0: return redirect(f"/pay/{user_id}")
    if filename not in FILES: return "not allowed",403
    cfg = get_protocols(user_id)
    if not cfg: return "VPS لم يجهز الملف - تأكد أن agent.py يخدم على بورت 5001",500
    lines=[]
    lines.append(f"# PREMIUM GATE - {user_id} - {filename}")
    lines.append(f"# Expire: {cfg.get('expire_at','')}")
    lines.append(f"# Host: {cfg.get('host','')}")
    lines.append("")
    if cfg.get("ssh"):
        s=cfg["ssh"]; lines.append(f"[SSH]\n{s.get('username')}:{s.get('password')}@{s.get('host')}:{s.get('port')}\n")
    if cfg.get("tls"):
        t=cfg["tls"]; lines.append(f"[TLS]\n{t.get('host')}:{t.get('port')} SNI={t.get('sni')}\n")
    if cfg.get("vless"): lines.append(f"[VLESS]\n{cfg['vless'].get('link','')}\n")
    if cfg.get("trojan"): lines.append(f"[TROJAN]\n{cfg['trojan'].get('link','')}\n")
    if cfg.get("vmess"): lines.append(f"[VMESS]\n{cfg['vmess'].get('link','')}\n")
    lines.append("\n# Full JSON:\n" + json.dumps(cfg, ensure_ascii=False, indent=2))
    txt="\n".join(lines)
    base=filename.rsplit(".",1)[0]; ext=filename.rsplit(".",1)[1] if "." in filename else "txt"
    out=f"{base}.{user_id[:12]}.{ext}"
    return Response(txt, mimetype='text/plain', headers={"Content-Disposition": f"attachment;filename={out}"})

@app.route('/api/protocols/<user_id>')
def api_protocols(user_id):
    cfg = get_protocols(user_id)
    if not cfg: return jsonify({"ok": False, "error": "VPS no blob"}), 500
    return jsonify({"ok": True, "user_id": user_id, "config": cfg, "all_links": cfg.get("all_links", {})})

@app.route('/api/agent/connect', methods=['POST'])
def api_agent_connect():
    data=request.get_json(silent=True) or {}
    blob=data.get("blob")
    if not blob: return jsonify({"error":"blob required"}),400
    try:
        r=requests.post(f"{AGENT_URL}/connect", headers={"X-Agent-Token": VPS_TOKEN}, json={"blob": blob}, timeout=10)
        return jsonify(r.json()), r.status_code
    except Exception as e: return jsonify({"error": str(e)}), 500

@app.route('/api/create_free', methods=['POST'])
def api_create_free():
    uid=(request.get_json(silent=True) or {}).get("user_id")
    if not uid: return jsonify({"error":"user_id required"}),400
    ok,res=agent_create_bundle(uid,"free")
    return jsonify({"ok":ok,"data":res}),200 if ok else 500

@app.route('/api/create_paid', methods=['POST'])
def api_create_paid():
    uid=(request.get_json(silent=True) or {}).get("user_id")
    if not uid: return jsonify({"error":"user_id required"}),400
    ok,res=agent_create_bundle(uid,"paid")
    return jsonify({"ok":ok,"data":res}),200 if ok else 500

@app.route('/api/madar/charge-card', methods=['POST'])
def madar_charge_card():
    data=request.get_json(silent=True) or {}
    user_id=data.get("user_id")
    card_code=str(data.get("card_code","")).strip().replace(" ","").replace("-","")
    if not card_code or len(card_code)<10: return jsonify({"status":"fail"})
    try:
        used=supabase.table("madar_cards_used").select("*").eq("card_code",card_code).execute()
        if used.data: return jsonify({"status":"used"})
        pending=supabase.table("madar_pending").select("*").eq("card_code",card_code).eq("status","pending").execute()
        if pending.data: return jsonify({"status":"used"})
    except: pass
    try: supabase.table("madar_pending").insert({"user_id":user_id,"card_code":card_code,"status":"pending"}).execute()
    except Exception as e: return jsonify({"status":"fail","error":str(e)})
    return jsonify({"status":"pending"})

@app.route("/admin")
def admin():
    if request.args.get("key") not in ALLOWED_KEYS: return Response(f"<h1>401</h1><p>/admin?key={ADMIN_KEY}</p>",401)
    return Response(ADMIN_HTML, mimetype='text/html')

@app.route("/admin/users")
def a_users():
    if request.args.get("key") not in ALLOWED_KEYS: return jsonify({"error":"key غلط"}),401
    if not supabase: return jsonify([])
    try: users=supabase.table("users").select("*").order("expires_at",desc=True).limit(200).execute().data or []
    except Exception as e: return jsonify({"error":str(e)}),500
    try: paid_ids={x["user_id"] for x in get_paid_users_list() if x.get("is_active")}
    except: paid_ids=set()
    out=[]
    for u in users:
        if u.get("user_id") in paid_ids: continue
        rs=u.get("status","active"); rem=get_remaining_hours(u)
        out.append({"user_id":u.get("user_id"),"expire_at":u.get("expires_at") or "","remaining":rem,"remaining_formatted":format_hm(rem) if rs!="inactive" else "معطل","raw_status":rs,"is_active":rs!="inactive" and rem>0,"is_paid":False,"ip_address":u.get("ip_address","")})
    return jsonify(out)

@app.route("/admin/paid")
def admin_paid():
    if request.args.get("key") not in ALLOWED_KEYS: return jsonify({"error":"no"}),401
    return jsonify(get_paid_users_list())

@app.route("/admin/usdt")
def admin_usdt():
    if request.args.get("key") not in ALLOWED_KEYS: return jsonify({"error":"no"}),401
    return jsonify([x for x in get_paid_users_list() if x.get("method")=="USDT"])

@app.route("/admin/vps/users")
def admin_vps_users():
    if request.args.get("key") not in ALLOWED_KEYS: return jsonify({"error":"no"}),401
    users=[]
    if supabase:
        try: users=supabase.table("users").select("*").order("expires_at",desc=True).limit(200).execute().data or []
        except: users=[]
    out=[]
    for u in users:
        uid=u.get("user_id")
        out.append({"user_id":uid,"expire_at":u.get("expires_at") or "","remaining":get_remaining_hours(u),"remaining_formatted":format_hm(get_remaining_hours(u)),"vps":agent_status(uid) or {"exists": False},"is_paid":is_paid_user(uid)})
    return jsonify(out)

@app.route("/admin/vps/create", methods=['POST'])
def admin_vps_create():
    if request.args.get("key") not in ALLOWED_KEYS: return jsonify({"message":"key غلط"}),401
    data=request.get_json(silent=True) or {}; uid=data.get("user_id"); plan=data.get("plan","free")
    if not uid: return jsonify({"message":"user_id ناقص"}),400
    ok,res=agent_create_bundle(uid, plan)
    if ok:
        hours = 2 if plan=="free" else 720
        exp=datetime.now()+timedelta(hours=hours)
        user=get_user(uid) or {"user_id":uid}
        user["expires_at"]=exp.strftime("%Y-%m-%d %H:%M:%S"); user["status"]="active"; save_user(user)
        return jsonify({"message":f"تم خلق {uid} في VPS - {plan}"})
    return jsonify({"message":f"فشل VPS: {res}"}),500

@app.route("/admin/vps/delete", methods=['POST'])
def admin_vps_delete():
    if request.args.get("key") not in ALLOWED_KEYS: return jsonify({"message":"key غلط"}),401
    uid=(request.get_json(silent=True) or {}).get("user_id")
    ok=agent_delete_bundle(uid)
    return jsonify({"message":f"تم حذف {uid} من VPS" if ok else "VPS ما لقاش اليوزر"})

@app.route("/admin/paid-extend", methods=['POST'])
def admin_paid_extend():
    if request.args.get("key") not in ALLOWED_KEYS: return jsonify({"message":"key غلط"}),401
    data=request.get_json(silent=True) or {}; uid=data.get("user_id")
    if not uid: return jsonify({"message":"user_id ناقص"}),400
    try:
        subs=supabase.table("subscriptions").select("*").eq("user_id",uid).eq("is_paid",True).execute().data or []
        if not subs: return jsonify({"message":"ماعنداش اشتراك"}),404
        best=max(subs,key=lambda s: parse_expire(s.get("expire_at") or "2000-01-01") or datetime(2000,1,1))
        old=parse_expire(best.get("expire_at")) or datetime.now()
        new=max(old,datetime.now())+timedelta(days=30)
        if best.get("id"): supabase.table("subscriptions").update({"expire_at":new.isoformat()}).eq("id",best.get("id")).execute()
        else: supabase.table("subscriptions").update({"expire_at":new.isoformat()}).eq("user_id",uid).eq("tx_hash",best.get("tx_hash")).execute()
        user=get_user(uid)
        if user: user["expires_at"]=new.strftime("%Y-%m-%d %H:%M:%S"); user["status"]="active"; save_user(user)
        agent_create_bundle(uid,"paid")
        return jsonify({"message":f"تم تمديد {uid} 30 يوم + تجديد VPS"})
    except Exception as e: return jsonify({"message":f"خطأ: {e}"}),500

@app.route("/admin/paid-delete", methods=['POST'])
def admin_paid_delete():
    if request.args.get("key") not in ALLOWED_KEYS: return jsonify({"error":"no"}),401
    uid=(request.get_json(silent=True) or {}).get("user_id")
    try:
        supabase.table("subscriptions").delete().eq("user_id",uid).execute()
        supabase.table("users").delete().eq("user_id",uid).execute()
        try: supabase.table("madar_cards_used").delete().eq("user_id",uid).execute()
        except: pass
        try: supabase.table("madar_pending").delete().eq("user_id",uid).execute()
        except: pass
        agent_delete_bundle(uid)
        return jsonify({"message":f"تم حذف {uid}"})
    except Exception as e: return jsonify({"message":str(e)}),500

@app.route("/admin/action", methods=['POST'])
def admin_action():
    if request.args.get("key") not in ALLOWED_KEYS: return jsonify({"message":"key غلط"}),401
    data=request.get_json(silent=True) or {}; uid=data.get("user_id"); act=data.get("action"); days=data.get("days",0); hours=data.get("hours",0)
    try:
        if is_paid_user(uid) and act in ["delete","disable","enable","add_days"]:
            return jsonify({"message":"هذا مدفوع - عدله من تب المدفوعين"}),400
        user=get_user(uid)
        if not user and act!="delete": return jsonify({"message":"اليوزر غير موجود"}),404
        if act=="delete":
            supabase.table("users").delete().eq("user_id",uid).execute(); agent_delete_bundle(uid)
            return jsonify({"message":f"تم حذف {uid}"})
        elif act=="disable":
            supabase.table("users").update({"status":"inactive"}).eq("user_id",uid).execute(); agent_delete_bundle(uid)
            return jsonify({"message":f"تم تعطيل {uid} + حذف من VPS"})
        elif act=="enable":
            supabase.table("users").update({"status":"active"}).eq("user_id",uid).execute(); agent_create_bundle(uid,"free")
            return jsonify({"message":f"تم تفعيل {uid} + خلق في VPS"})
        elif act=="extend_custom" or act=="add_days":
            cur=parse_expire(user.get("expires_at")) if user else datetime.now()
            if not cur or cur<datetime.now(): cur=datetime.now()
            new=cur+timedelta(days=int(days),hours=int(hours))
            supabase.table("users").update({"expires_at":new.strftime("%Y-%m-%d %H:%M:%S"),"status":"active"}).eq("user_id",uid).execute()
            return jsonify({"message":"تم التحديث"})
    except Exception as e: return jsonify({"message":f"خطأ: {e}"}),500
    return jsonify({"message":"unknown"})

@app.route("/admin/support")
def admin_support():
    if request.args.get("key") not in ALLOWED_KEYS: return jsonify({"error":"no"}),401
    try:
        res=supabase.table("support_messages").select("*").order("created_at",desc=True).limit(200).execute()
        return jsonify(res.data or [])
    except: return jsonify([])

@app.route("/admin/devices")
def admin_devices():
    if request.args.get("key") not in ALLOWED_KEYS: return jsonify({"error":"no"}),401
    try:
        res=supabase.table("device_limits").select("*").execute()
        return jsonify(res.data or [])
    except: return jsonify([])

@app.route("/admin/devices/delete", methods=['POST'])
def admin_devices_delete():
    if request.args.get("key") not in ALLOWED_KEYS: return jsonify({"error":"no"}),401
    data=request.get_json(silent=True) or {}
    try: supabase.table("device_limits").delete().eq("fingerprint",data.get("fingerprint")).execute()
    except: pass
    return jsonify({"message":"تم"})

@app.route("/admin/devices/clear", methods=['POST'])
def admin_devices_clear():
    if request.args.get("key") not in ALLOWED_KEYS: return jsonify({"error":"no"}),401
    try: supabase.table("device_limits").delete().neq("fingerprint","___none___").execute()
    except: pass
    return jsonify({"message":"تم المسح"})

@app.route("/admin/madar-pending")
def admin_madar_pending():
    if request.args.get("key") not in ALLOWED_KEYS: return jsonify({"error":"no"}),401
    try:
        res=supabase.table("madar_pending").select("*").order("created_at",desc=True).limit(200).execute()
        return jsonify(res.data or [])
    except: return jsonify([])

@app.route("/admin/madar-approve", methods=['POST'])
def admin_madar_approve():
    if request.args.get("key") not in ALLOWED_KEYS: return jsonify({"error":"no"}),401
    data=request.get_json(silent=True) or {}; pid=data.get("id"); uid=data.get("user_id"); card=data.get("card_code","")
    try:
        supabase.table("madar_pending").update({"status":"approved"}).eq("id",pid).execute()
        try: supabase.table("madar_cards_used").insert({"user_id":uid,"card_code":card}).execute()
        except: pass
        madar_activate(uid)
        return jsonify({"message":f"تم تفعيل {uid} - 30 يوم + VPS paid"})
    except Exception as e: return jsonify({"message":f"خطأ: {e}"}),500

@app.route("/admin/madar-reject", methods=['POST'])
def admin_madar_reject():
    if request.args.get("key") not in ALLOWED_KEYS: return jsonify({"error":"no"}),401
    pid=(request.get_json(silent=True) or {}).get("id")
    try:
        supabase.table("madar_pending").update({"status":"rejected"}).eq("id",pid).execute()
        return jsonify({"ok":True})
    except Exception as e: return jsonify({"error":str(e)}),500

if __name__ == '__main__':
    print(f"=== PROMAX V2 - 4 PAGES ===")
    print(f"Home: http://localhost:{PORT}/")
    print(f"Admin: http://localhost:{PORT}/admin?key={ADMIN_KEY}")
    print(f"VPS: {VPS_HOST}")
    app.run(host='0.0.0.0', port=PORT)

# app.py - 1/3 - 4 صفحات فقط - PROMAX V2
from flask import Flask, request, jsonify, Response, redirect, make_response
from datetime import datetime, timedelta, timezone
from supabase import create_client, Client
import requests, random, string, json

app = Flask(__name__)

# ===== عدل هنا بس - يقرا من Render =====
import os
from supabase import create_client, Client

VPS_TOKEN = os.getenv("VPS_TOKEN", "vps_libya_2026_8rT9yU2iO5p")
SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")
ADMIN_KEY = os.getenv("ADMIN_KEY", "123456")
ROOT_WALLET = os.getenv("ROOT_WALLET", "0x2d447f9d656594f6c65de039aebe7da32a968400")
VPS_HOST = os.getenv("VPS_HOST", "YOUR_VPS_IP")
DOMAIN = os.getenv("DOMAIN", "").strip() or VPS_HOST  # لو فاضي في Render، يستعمل IP
PORT = int(os.getenv("PORT", 5000))

ALLOWED_KEYS = [ADMIN_KEY, "123456", "admin123"]

# حماية - لو Supabase مش محطوط في Render، ما يطيحش السيرفر
try:
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY) if SUPABASE_URL.startswith("http") else None
except Exception as e:
    print("Supabase init failed:", e)
    supabase = None
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
ADMIN_HTML = """<!DOCTYPE html><html dir="rtl" lang="ar"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Admin PRO</title><style>*{box-sizing:border-box;margin:0;padding:0}body{background:#050507;color:#fff;font-family:system-ui;padding:12px}.top{display:flex;justify-content:space-between;align-items:center;gap:8px;flex-wrap:wrap}.stats{display:grid;grid-template-columns:repeat(5,1fr);gap:8px;margin-top:12px}.stat{background:#12121f;border:1px solid #222;border-radius:12px;padding:10px}.stat p{font-size:11px;color:#888}.stat b{font-size:19px}.tabs{display:flex;gap:6px;margin-top:12px;overflow-x:auto}.tabs button{background:#12121f;color:#fff;border:1px solid #222;padding:8px 12px;border-radius:12px;font-size:12px;cursor:pointer;white-space:nowrap}.tabs button.on{background:#fff;color:#000;font-weight:900}.box{background:#12121f;border:1px solid #222;border-radius:16px;padding:12px;margin-top:12px}.item{background:#000;border:1px solid #1e1e1e;border-radius:12px;padding:10px;margin-top:8px}.item p{font-size:11px;color:#888;margin-top:4px}.row{display:flex;gap:6px;flex-wrap:wrap;margin-top:8px}.btn{padding:7px 10px;border:none;border-radius:8px;font-size:12px;font-weight:700;cursor:pointer}.g{background:#22c55e;color:#000}.y{background:#facc15;color:#000}.v{background:#7c3aed;color:#fff}.w{background:#fff;color:#000}.r{background:#ef4444;color:#fff}.gray{background:#222;color:#fff}.badge{font-size:10px;padding:3px 7px;border-radius:20px}.badge-g{background:#22c55e33;color:#4ade80}.badge-r{background:#ef444433;color:#f87171}.badge-y{background:#facc1533;color:#facc15}.inp{background:#000;border:1px solid #333;border-radius:8px;padding:7px;color:#fff;width:70px}.rep{flex:1;background:#000;border:1px solid #333;border-radius:8px;padding:7px;color:#fff;min-width:120px}.filt{display:flex;gap:6px;margin-top:10px;flex-wrap:wrap}.loading{text-align:center;color:#888;padding:30px;font-size:14px}.hidden{display:none}</style></head><body><div class="top"><h1>PROMAX V2 - PRO</h1><div style="display:flex;gap:6px;align-items:center"><input id="search" oninput="renderCurrent()" placeholder="بحث user_id" style="background:#12121f;border:1px solid #222;border-radius:10px;padding:7px 10px;color:#fff;font-size:12px;width:150px"><button onclick="refreshAll()" class="btn w">تحديث</button></div></div><div class="stats"><div class="stat"><p>مجاني</p><b id="cFree">--</b></div><div class="stat"><p>نشط</p><b id="cActive">--</b></div><div class="stat"><p>منتهي</p><b id="cExp">--</b></div><div class="stat"><p>مدفوع</p><b id="cPaid">--</b></div><div class="stat"><p>اجهزة</p><b id="cDev">--</b></div></div><div class="tabs"><button onclick="showTab('madar')" id="tab-madar">كروت المدار <span id="bMadar"></span></button><button onclick="showTab('usdt')" id="tab-usdt">USDT</button><button onclick="showTab('paid')" id="tab-paid" class="on">المشتركين</button><button onclick="showTab('users')" id="tab-users">المستخدمين</button><button onclick="showTab('vps')" id="tab-vps">VPS</button><button onclick="showTab('support')" id="tab-support">الدعم</button><button onclick="showTab('devices')" id="tab-devices">الاجهزة</button></div><div class="box"><div style="display:flex;justify-content:space-between;flex-wrap:wrap;gap:8px"><b id="boxTitle">المشتركين</b><div>تمديد مخصص: <input id="customDays" type="number" placeholder="ايام" class="inp"> <input id="customHours" type="number" placeholder="ساعات" class="inp"></div></div><div id="filt" class="filt"></div><div id="box"><div class="loading">جاري التحميل...</div></div></div><script>var KEY=new URLSearchParams(location.search).get("key")||"123456";var cur="paid";var USERS=[],PAID=[],MADAR=[],USDT=[],SUP=[],DEV=[],VPS=[];var paidF="all";var supF="all";async function loadStats(){try{var u=await fetch("/admin/users?key="+KEY).then(function(r){return r.json()}).catch(function(){return []});USERS=u;var p=await fetch("/admin/paid?key="+KEY).then(function(r){return r.json()}).catch(function(){return []});PAID=p;document.getElementById("cFree").innerText=USERS.length;document.getElementById("cActive").innerText=USERS.filter(function(x){return x.is_active}).length;document.getElementById("cExp").innerText=USERS.filter(function(x){return !x.is_active}).length;document.getElementById("cPaid").innerText=PAID.length;}catch(e){}}async function loadCurrentTab(){document.getElementById("box").innerHTML="<div class='loading'>جاري التحميل...</div>";var url="";if(cur=="paid")url="/admin/paid?key="+KEY;else if(cur=="users")url="/admin/users?key="+KEY;else if(cur=="madar")url="/admin/madar-pending?key="+KEY;else if(cur=="usdt")url="/admin/usdt?key="+KEY;else if(cur=="support")url="/admin/support?key="+KEY;else if(cur=="devices")url="/admin/devices?key="+KEY;else if(cur=="vps")url="/admin/vps/users?key="+KEY;var data=await fetch(url).then(function(r){return r.json()}).catch(function(){return []});if(cur=="paid")PAID=data;else if(cur=="users")USERS=data;else if(cur=="madar"){MADAR=data;var pend=MADAR.filter(function(x){return x.status=="pending"}).length;document.getElementById("bMadar").innerText=pend?"("+pend+")":"";}else if(cur=="usdt")USDT=data;else if(cur=="support")SUP=data;else if(cur=="devices"){DEV=data;document.getElementById("cDev").innerText=DEV.length;}else if(cur=="vps")VPS=data;renderCurrent();}async function refreshAll(){await loadCurrentTab();loadStats();}function showTab(t){cur=t;var btns=document.querySelectorAll(".tabs button");for(var i=0;i<btns.length;i++){btns[i].classList.remove("on")}document.getElementById("tab-"+t).classList.add("on");var titles={madar:"كروت المدار",usdt:"USDT",paid:"المشتركين",users:"المستخدمين",vps:"VPS",support:"الدعم",devices:"الاجهزة"};document.getElementById("boxTitle").innerText=titles[t];var f=document.getElementById("filt");if(t=="paid"){f.innerHTML="<button onclick=setPaidF('all') class='btn w'>الكل</button><button onclick=setPaidF('مدار') class='btn y'>مدار</button><button onclick=setPaidF('USDT') class='btn g'>USDT</button>"}else{f.innerHTML=""}loadCurrentTab();}function setPaidF(v){paidF=v;renderCurrent()}function renderCurrent(){var q=(document.getElementById("search").value||"").trim();var box=document.getElementById("box");var h="";if(cur=="users"){USERS.filter(function(x){return !q||x.user_id.indexOf(q)>=0}).forEach(function(x){h+="<div class='item'><b>"+x.user_id+"</b> "+(x.is_active?"<span class='badge badge-g'>فعال</span>":"<span class='badge badge-r'>منتهي</span>")+"<p>متبقي: "+x.remaining_formatted+" | "+x.expire_at+"</p><div class='row'><button onclick=actUser('"+x.user_id+"','extend_custom') class='btn v'>+ مخصص</button><button onclick=actUser('"+x.user_id+"','add_days') class='btn g'>+30 يوم</button><button onclick=actUser('"+x.user_id+"','enable') class='btn w'>تفعيل</button><button onclick=actUser('"+x.user_id+"','disable') class='btn y'>تعطيل</button><button onclick=actUser('"+x.user_id+"','delete') class='btn r'>حذف</button><a href='/view/"+x.user_id+"' target='_blank' class='btn gray' style='text-decoration:none'>فتح صفحته</a></div></div>"});}else if(cur=="madar"){MADAR.filter(function(x){return !q||x.user_id.indexOf(q)>=0}).forEach(function(x){h+="<div class='item'><b>"+x.user_id+"</b> <span class='badge badge-y'>"+x.status+"</span><p style='font-size:14px;color:#fff'>"+x.card_code+"</p><p>"+x.created_at+"</p><div class='row'>"+(x.status=="pending"?"<button onclick=approveMadar("+x.id+",'"+x.user_id+"','"+x.card_code+"') class='btn g'>تفعيل بعد الشحن</button><button onclick=rejectMadar("+x.id+") class='btn r'>رفض</button>":"")+"</div></div>"});}else if(cur=="usdt"){USDT.forEach(function(x){h+="<div class='item'><b>"+x.user_id+"</b><p>"+(x.tx_hash||"")+"</p><p>متبقي: "+x.remaining_formatted+"</p><div class='row'><a href='/view/"+x.user_id+"' target='_blank' class='btn w' style='text-decoration:none'>فتح حسابه</a><button onclick=delPaid('"+x.user_id+"') class='btn r'>حذف</button></div></div>"});}else if(cur=="paid"){PAID.filter(function(x){return paidF=="all"||x.method==paidF}).filter(function(x){return !q||x.user_id.indexOf(q)>=0}).forEach(function(x){h+="<div class='item'><b>"+x.user_id+"</b> <span class='badge badge-g'>"+x.method+"</span><p>متبقي: "+x.remaining_formatted+" | "+x.expire_at+"</p><div class='row'><a href='/view/"+x.user_id+"' target='_blank' class='btn w' style='text-decoration:none'>فتح حسابه</a><button onclick=extendPaid('"+x.user_id+"') class='btn v'>+30 يوم</button><button onclick=viewProto('"+x.user_id+"') class='btn gray'>بروتوكولات</button><button onclick=delPaid('"+x.user_id+"') class='btn r'>حذف نهائي</button></div></div>"});}else if(cur=="vps"){VPS.forEach(function(x){h+="<div class='item'><b>"+x.user_id+"</b> "+(x.vps&&x.vps.exists?"<span class='badge badge-g'>VPS</span>":"<span class='badge badge-r'>مافيش VPS</span>")+"<p>متبقي: "+x.remaining_formatted+"</p><div class='row'><button onclick=vpsUser('"+x.user_id+"','free') class='btn v'>انشاء Free</button><button onclick=vpsUser('"+x.user_id+"','paid') class='btn g'>انشاء Paid</button><button onclick=vpsUser('"+x.user_id+"','delete') class='btn r'>حذف VPS</button><button onclick=viewProto('"+x.user_id+"') class='btn gray'>بروتوكولات</button></div></div>"});}else if(cur=="support"){var groups={};SUP.forEach(function(m){if(!groups[m.user_id])groups[m.user_id]=[];groups[m.user_id].push(m)});var btns="<button onclick=setSupF('all') class='btn w'>الكل</button>";Object.keys(groups).forEach(function(uid){btns+="<button onclick=setSupF('"+uid+"') class='btn gray'>"+uid+"</button>"});document.getElementById("filt").innerHTML=btns;SUP.filter(function(m){return supF=="all"||m.user_id==supF}).forEach(function(m){h+="<div class='item'><b>"+m.user_id+"</b><p>"+m.created_at+"</p><p style='color:#fff;font-size:13px'>"+m.message+"</p><div class='row'><input id='rep-"+m.id+"' class='rep' placeholder='رد...'><button onclick=replySupport('"+m.user_id+"',"+m.id+") class='btn w'>رد</button></div></div>"});}else if(cur=="devices"){DEV.forEach(function(x){h+="<div class='item'><b>"+x.fingerprint+"</b><p>"+x.user_id+"</p><div class='row'><button onclick=delDev('"+x.fingerprint+"') class='btn r'>حذف الجهاز</button></div></div>"});if(DEV.length)h+="<button onclick=clearDev() class='btn r' style='width:100%;margin-top:10px'>مسح كل الاجهزة</button>";}box.innerHTML=h||"<div class='item' style='text-align:center;color:#888'>لا يوجد</div>";}function setSupF(v){supF=v;renderCurrent()}async function actUser(uid,act){var days=0;var hours=0;if(act=="extend_custom"){days=parseInt(document.getElementById("customDays").value)||0;hours=parseInt(document.getElementById("customHours").value)||0;if(!days&&!hours){alert("اكتب الايام او الساعات");return}}if(act=="add_days")days=30;if(!confirm(act+" ل "+uid+" ؟"))return;var r=await fetch("/admin/action?key="+KEY,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({user_id:uid,action:act,days:days,hours:hours})}).then(function(x){return x.json()});alert(r.message||"تم");refreshAll();}async function approveMadar(id,uid,card){if(!confirm("شحنت الكرت "+card+" ؟"))return;var r=await fetch("/admin/madar-approve?key="+KEY,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({id:id,user_id:uid,card_code:card})}).then(function(x){return x.json()});alert(r.message||"تم");refreshAll();}async function rejectMadar(id){if(!confirm("رفض الكرت؟"))return;await fetch("/admin/madar-reject?key="+KEY,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({id:id})});refreshAll();}async function extendPaid(uid){if(!confirm("تمديد 30 يوم ل "+uid+" ؟"))return;var r=await fetch("/admin/paid-extend?key="+KEY,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({user_id:uid})}).then(function(x){return x.json()});alert(r.message||"تم");refreshAll();}async function delPaid(uid){if(!confirm("حذف اشتراك "+uid+" ؟"))return;await fetch("/admin/paid-delete?key="+KEY,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({user_id:uid})});refreshAll();}async function viewProto(uid){var r=await fetch("/api/protocols/"+uid).then(function(x){return x.json()});alert(JSON.stringify(r.config||r,null,2).slice(0,2000));}async function vpsUser(uid,act){var url=act=="delete"?"/admin/vps/delete?key="+KEY:"/admin/vps/create?key="+KEY;var body=act=="delete"?{user_id:uid}:{user_id:uid,plan:act};var r=await fetch(url,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(body)}).then(function(x){return x.json()});alert(r.message||JSON.stringify(r));refreshAll();}async function replySupport(uid,id){var txt=document.getElementById("rep-"+id).value.trim();if(!txt)return;await fetch("/api/support/send",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({user_id:uid,message:txt,sender:"admin"})});alert("تم الرد");refreshAll();}async function delDev(fp){await fetch("/admin/devices/delete?key="+KEY,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({fingerprint:fp})});refreshAll();}async function clearDev(){if(!confirm("مسح كل الاجهزة؟"))return;await fetch("/admin/devices/clear?key="+KEY,{method:"POST"});refreshAll();}loadCurrentTab();loadStats();</script></body></html>"""

MADAR_HTML = """<!DOCTYPE html><html dir="rtl" lang="ar"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>دفع بالمدار</title><style>*{box-sizing:border-box;margin:0;padding:0}body{background:#050507;color:#fff;font-family:system-ui;padding:16px}.wrap{max-width:420px;margin:0 auto}.back{color:#888;font-size:13px;text-decoration:none}.box{background:#12121f;border:1px solid #222;border-radius:20px;padding:20px;margin-top:14px;text-align:center}.box h1{font-size:19px}.box p{color:#facc15;font-size:12px;margin-top:8px}.inp{width:100%;background:#000;border:1px solid #333;border-radius:12px;padding:16px;text-align:center;color:#fff;margin-top:16px;font-size:18px;font-weight:700;letter-spacing:3px;outline:none}.btn{width:100%;padding:15px;border:none;border-radius:12px;font-weight:900;font-size:15px;margin-top:12px;cursor:pointer;background:#facc15;color:#000}.btn:disabled{opacity:.6}.msg{text-align:center;font-size:14px;margin-top:12px;min-height:20px;color:#f87171}.msg.ok{color:#4ade80}.msg.wait{color:#facc15}.done{background:#14532d;border:1px solid #22c55e;border-radius:12px;padding:14px;margin-top:14px}.done b{color:#4ade80}.done p{color:#aaa;font-size:12px;margin-top:6px}.done a{display:block;background:#fff;color:#000;padding:11px;border-radius:10px;font-weight:700;font-size:14px;text-decoration:none;margin-top:12px}.hidden{display:none}</style></head><body><div class="wrap"><a href="/pay/__UID__" class="back">← رجوع للدفع</a><div class="box"><h1>💳 دفع بالمدار - 10 دينار</h1><p>سيتم مراجعته يدويا وتفعيل حسابك 30 يوم</p><div id="form"><input id="card" inputmode="numeric" placeholder="رقم الكرت السري" maxlength="20" class="inp"><button id="btn" onclick="sendMadar()" class="btn">ارسال الكرت للمراجعة</button></div><p id="msg" class="msg"></p><div id="done" class="done hidden"><b>✅ تم ارسال الكرت</b><p>انتظر تفعيل حسابك من الادمن</p><a href="/view/__UID__">الرجوع لحسابي</a></div></div></div><script>const UID="__UID__";async function sendMadar(){let c=document.getElementById('card').value.trim();let btn=document.getElementById('btn');let msg=document.getElementById('msg');if(c.length<10){msg.className='msg';msg.innerText='اكتب الرقم كامل';return;}btn.disabled=true;btn.innerText='⏳ جاري الارسال...';msg.className='msg wait';msg.innerText='جاري الارسال...';try{let r=await fetch('/api/madar/charge-card',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({user_id:UID,card_code:c})}).then(x=>x.json());btn.disabled=false;btn.innerText='ارسال الكرت للمراجعة';if(r.status=='pending'){document.getElementById('form').classList.add('hidden');msg.className='hidden';document.getElementById('done').classList.remove('hidden');}else if(r.status=='used'){msg.className='msg';msg.innerText='❌ الكرت مستعمل من قبل';}else{msg.className='msg';msg.innerText='❌ خطأ، حاول مرة اخرى';}}catch(e){btn.disabled=false;btn.innerText='ارسال الكرت للمراجعة';msg.className='msg';msg.innerText='❌ خطأ في الاتصال، حاول تاني';}}</script></body></html>"""

HOME_HTML = """<!DOCTYPE html><html dir="rtl" lang="ar"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>PREMIUM GATE</title><style>*{box-sizing:border-box;margin:0;padding:0}body{background:#050507;color:#fff;font-family:system-ui;padding:16px}.top{display:flex;justify-content:space-between;align-items:center}.badge{background:#12121f;border:1px solid #222;padding:6px 12px;border-radius:20px;font-size:12px;color:#4ade80}.center{text-align:center;margin-top:20px}.center h1{font-size:32px;line-height:1.3}.grad{color:#a78bfa}.center p{color:#999;font-size:14px;margin-top:10px}.btn{display:block;background:#fff;color:#000;padding:16px;border-radius:14px;font-weight:900;font-size:17px;text-align:center;margin-top:18px;text-decoration:none}.grid{display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px;margin-top:14px}.card{background:#12121f;border:1px solid #222;border-radius:14px;padding:12px;text-align:center}.box{background:#12121f;border:1px solid #222;border-radius:16px;padding:14px;margin-top:16px}.row{display:flex;gap:8px;margin-top:12px}.row a{flex:1;text-align:center;padding:11px;border-radius:10px;font-weight:700;font-size:14px;text-decoration:none}.vio{background:#7c3aed;color:#fff}.green{background:#4ade80;color:#000}.chat{position:fixed;bottom:16px;right:16px;width:48px;height:48px;background:#fff;color:#000;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:20px;cursor:pointer}.chatbox{position:fixed;bottom:70px;right:12px;width:340px;max-width:92vw;background:#12121f;border:1px solid #222;border-radius:16px;display:none;flex-direction:column;overflow:hidden}.chatbox.open{display:flex}.chead{padding:12px;background:#1a1a2e;display:flex;justify-content:space-between}.msgs{padding:12px;max-height:300px;overflow-y:auto}.msgs div{background:#222;padding:8px;border-radius:10px;margin-top:6px;font-size:13px}.cfoot{padding:10px;display:flex;gap:6px}.cfoot input{flex:1;background:#000;border:1px solid #333;border-radius:10px;padding:10px;color:#fff;outline:none}.cfoot button{background:#fff;color:#000;border:none;padding:10px 14px;border-radius:10px;font-weight:700}</style></head><body><div class="top"><b>P PREMIUM GATE</b><span class="badge">● شغال</span></div><div class="center"><h1>دخولك للمحتوى<br><span class="grad">في ثانية واحدة</span></h1><p>رابط واحد ينشئلك حساب، يعطيك ساعتين مجانا.</p><a href="/go" class="btn">🚀 إنشاء حساب ودخول فوري</a><div class="grid"><div class="card"><b>2H</b><br><span style="color:#888;font-size:12px">مجانا</span></div><div class="card"><b>1$</b><br><span style="color:#888;font-size:12px">30 يوم</span></div><div class="card"><b>∞</b><br><span style="color:#888;font-size:12px">تحميل</span></div></div></div><div class="box"><b style="font-size:13px;color:#aaa">● معاينة حسابك</b><div style="margin-top:10px"><b id="myid">user_------</b><p style="font-size:14px;color:#ccc;margin-top:6px">متبقي: <span id="mytime" style="color:#4ade80;font-weight:700">--:--:--</span> | <span id="mystatus">...</span></p><div class="row"><a id="mylib" href="#" class="vio">📁 محتوى</a><a id="mypay" href="#" class="green">💳 دفع</a></div></div></div><div class="chat" onclick="openChat()">💬</div><div id="chatBox" class="chatbox"><div class="chead"><div><b style="font-size:13px">💬 الدعم الفوري</b><p style="font-size:11px;color:#4ade80">● متصل الآن</p></div><button onclick="closeChat()" style="background:none;border:none;color:#888;cursor:pointer">✕</button></div><div id="chatMsgs" class="msgs"><div>مرحبا! 👋 انا الدعم، كيف نساعدك؟</div></div><div class="cfoot"><input id="chatInput" placeholder="اكتب رسالتك..."><button onclick="sendMsg()">ارسال</button></div></div><script>let SUPPORT_UID=localStorage.getItem('support_uid')||"guest_"+Math.floor(Math.random()*99999);localStorage.setItem('support_uid',SUPPORT_UID);function openChat(){document.getElementById('chatBox').classList.add('open');loadMsgs();}function closeChat(){document.getElementById('chatBox').classList.remove('open');}async function loadMsgs(){try{let r=await fetch('/api/support/get?user_id='+SUPPORT_UID).then(x=>x.json());let box=document.getElementById('chatMsgs');let h='<div>مرحبا! 👋 انا الدعم، كيف نساعدك؟</div>';r.forEach(m=>{h+='<div style="'+(m.sender==='user'?'background:#fff;color:#000;margin-left:20px':'')+'">'+m.message+'</div>';});box.innerHTML=h;box.scrollTop=box.scrollHeight;}catch(e){}}async function sendMsg(){let inp=document.getElementById('chatInput');let txt=inp.value.trim();if(!txt) return;await fetch('/api/support/send',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({user_id:SUPPORT_UID,message:txt,sender:'user'})});inp.value='';loadMsgs();}let uid=localStorage.getItem('last_uid')||document.cookie.match(/last_user_id=([^;]+)/)?.[1];if(uid){document.getElementById('myid').innerText=uid;document.getElementById('mylib').href='/view/'+uid;document.getElementById('mypay').href='/pay/'+uid;fetch('/check?user_id='+uid).then(r=>r.json()).then(d=>{document.getElementById('mytime').innerText=d.hours||'0:00:00';document.getElementById('mystatus').innerText=d.status||'';});}else{document.getElementById('mystatus').innerText='مافيش حساب';}</script></body></html>"""

PAY_HTML = """<!DOCTYPE html><html dir="rtl" lang="ar"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>الدفع</title><style>*{box-sizing:border-box;margin:0;padding:0}body{background:#050507;color:#fff;font-family:system-ui;padding:16px}.wrap{max-width:420px;margin:0 auto}.back{color:#888;font-size:13px;text-decoration:none}.box{background:#12121f;border:1px solid #222;border-radius:20px;padding:18px;margin-top:14px}.box h1{text-align:center;font-size:18px}.amt{background:#000;border-radius:12px;padding:12px;margin-top:12px;display:flex;justify-content:space-between;align-items:center}.amt b{color:#4ade80;font-size:19px}.wal{background:#000;border-radius:12px;padding:12px;margin-top:10px}.wal p{font-size:12px;color:#888}.wal b{font-size:13px;word-break:break-all}.mini{background:#222;color:#fff;border:none;padding:7px 10px;border-radius:8px;font-size:12px;cursor:pointer}.btn{width:100%;padding:14px;border:none;border-radius:12px;font-weight:900;font-size:15px;margin-top:12px;cursor:pointer}.green{background:#4ade80;color:#000}.yellow{b
ackground:#facc15;color:#000}.btn:disabled{opacity:.6}.inp{width:100%;background:#000;border:1px solid #333;border-radius:12px;padding:14px;text-align:center;color:#fff;margin-top:12px;font-size:15px;outline:none}.hidden{display:none}.msg{text-align:center;font-size:14px;margin-top:12px;min-height:20px;color:#f87171}.msg.ok{color:#4ade80}.msg.wait{color:#facc15}</style></head><body><div class="wrap"><a href="/" class="back">← رجوع</a><div id="usdtBox" class="box"><h1>الدفع الآمن - USDT (BEP20)</h1><div class="amt"><b>USDT <span id="amt">...</span></b><button onclick="copyAmt()" class="mini">📋 نسخ المبلغ</button></div><div class="wal"><p>عنوان المحفظة</p><b dir="ltr">__WALLET__</b><br><button onclick="copyWallet()" class="mini" style="margin-top:8px">📋 نسخ المحفظة</button></div><button id="vbtn" class="btn green" onclick="verifyPay()">لقد دفعت، فعل حسابي</button><button onclick="showMadar()" class="btn yellow">💳 الدفع بالمدار - 10 دينار</button><p id="verifyMsg" class="msg"></p></div><div id="madarBox" class="box hidden"><h1>دفع بالمدار - 10 دينار</h1><p style="text-align:center;font-size:12px;color:#facc15;margin-top:6px">سيتم مراجعته يدويا وتفعيل حسابك</p><input id="card" placeholder="رقم الكرت السري" class="inp"><button id="madarBtn" onclick="sendMadar()" class="btn yellow">ارسال الكرت للمراجعة</button><p id="madarMsg" class="msg"></p><button onclick="showUsdt()" class="btn" style="background:#222;color:#aaa;font-size:12px">← رجوع لـ USDT</button></div></div><script>const UID="__UID__";const WALLET="__WALLET__";let AMT="";fetch('/amount/'+UID).then(r=>r.json()).then(d=>{AMT=d.amount;document.getElementById('amt').innerText=d.amount;});function copyAmt(){navigator.clipboard.writeText(AMT);}function copyWallet(){navigator.clipboard.writeText(WALLET);}async function verifyPay(){let btn=document.getElementById('vbtn');let msg=document.getElementById('verifyMsg');btn.disabled=true;btn.innerText='⏳ جاري التحقق...';msg.className='msg wait';msg.innerText='جاري التحقق من التحويل...';try{let r=await fetch('/verify/'+UID).then(r=>r.json());if(r.paid){btn.innerText='✅ تم التفعيل';msg.className='msg ok';msg.innerText='تم التفعيل 30 يوم ✅';setTimeout(()=>{location.href='/view/'+UID;},1200);}else{btn.disabled=false;btn.innerText='لقد دفعت، فعل حسابي';msg.className='msg';msg.innerText='لم يتم العثور على الدفع';}}catch(e){btn.disabled=false;btn.innerText='لقد دفعت، فعل حسابي';msg.className='msg';msg.innerText='لم يتم العثور - حاول تاني';}}function showMadar(){document.getElementById('usdtBox').classList.add('hidden');document.getElementById('madarBox').classList.remove('hidden');}function showUsdt(){document.getElementById('madarBox').classList.add('hidden');document.getElementById('usdtBox').classList.remove('hidden');}async function sendMadar(){let c=document.getElementById('card').value.trim();let btn=document.getElementById('madarBtn');let msg=document.getElementById('madarMsg');if(!c){msg.innerText='اكتب رقم الكرت';return;}btn.disabled=true;btn.innerText='⏳ جاري الارسال...';msg.className='msg wait';msg.innerText='جاري الارسال...';let r=await fetch('/api/madar/charge-card',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({user_id:UID,card_code:c})}).then(r=>r.json());btn.disabled=false;btn.innerText='ارسال الكرت للمراجعة';if(r.status=='pending'){msg.className='msg ok';msg.innerText='✅ تم ارسال الكرت، انتظر تفعيل الأدمن';}else if(r.status=='used'){msg.className='msg';msg.innerText='❌ الكرت مستعمل من قبل';}else{msg.className='msg';msg.innerText='❌ خطأ، حاول تاني';}}</script></body></html>"""

CONTENT_HTML = """<!DOCTYPE html><html dir="rtl" lang="ar"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>مكتبتك</title><style>*{box-sizing:border-box;margin:0;padding:0}body{background:#050507;color:#fff;font-family:system-ui;padding:16px}.top{display:flex;justify-content:space-between}.top a{background:#12121f;padding:6px 12px;border-radius:20px;font-size:12px;color:#fff;text-decoration:none}.center{text-align:center;margin-top:14px}.center h1{font-size:26px;line-height:1.3}.grad{color:#a78bfa}.center p{color:#999;font-size:13px;margin-top:8px}.info{display:flex;gap:8px;margin-top:14px}.info div{flex:1;background:#12121f;border:1px solid #222;border-radius:12px;padding:10px;display:flex;justify-content:space-between;font-size:13px}.timer{background:#12121f;border:1px solid #222;border-radius:16px;padding:16px;margin-top:12px;text-align:center}.timer b{font-size:28px}.btns{display:flex;gap:8px;justify-content:center;margin-top:12px}.btns a,.btns button{padding:10px 18px;border-radius:10px;font-weight:700;font-size:14px;border:none;cursor:pointer;text-decoration:none}.green{background:#4ade80;color:#000}.gray{background:#222;color:#fff}.proto{margin-top:12px}.pcard{background:#12121f;border:1px solid #222;border-radius:12px;padding:10px;margin-top:8px}.pcard p{font-size:12px;color:#ccc;word-break:break-all;margin-top:4px}.pcard button{background:#fff;color:#000;border:none;padding:5px 10px;border-radius:8px;font-size:12px;font-weight:700;float:left}.search{background:#12121f;border:1px solid #222;border-radius:12px;padding:10px;margin-top:12px;display:flex;gap:8px}.search input{background:none;border:none;outline:none;color:#fff;flex:1}.list{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-top:12px}.file{background:#12121f;border:1px solid #222;border-radius:12px;padding:12px}.file a{display:block;background:#fff;color:#000;text-align:center;padding:8px;border-radius:8px;font-weight:700;font-size:12px;text-decoration:none;margin-top:8px}</style></head><body><div class="top"><b>P PREMIUM GATE</b><div><a href="/">🏠 الرئيسية</a> <a href="#">👤 حسابي</a></div></div><div class="center"><h1>مكتبتك الخاصة<br><span class="grad">كل ملفاتك في مكان واحد</span></h1><p>حمّل أي ملف بضغطة واحدة.</p></div><div class="info"><div><span>📁 الملفات</span><b>7 ملف</b></div><div><span>👤 ID</span><b>__UID__</b></div></div><div class="timer"><div style="font-size:12px;color:#888">متبقي</div><b id="time">--:--:--</b><div id="status" style="color:#4ade80;font-size:13px;font-weight:700">نشط</div><div class="btns"><a href="/pay/__UID__" class="green">💳 تجديد</a><button onclick="loadProto()" class="gray">حسابي - بروتوكولات</button></div></div><div id="proto" class="proto"></div><div class="search"><span>🔍</span><input id="search" oninput="filterFiles()" placeholder="دوّر على ملف..."></div><div id="list" class="list"></div><script>const UID="__UID__";async function load(){let c=await fetch('/check?user_id='+UID).then(r=>r.json());document.getElementById('time').innerText=c.hours||'0:00:00';document.getElementById('status').innerText=c.status=='cooldown'?'انتهى':'نشط';let h="";(c.files||[]).forEach(f=>{h+='<div class="file file-card" data-name="'+f+'"><b style="font-size:13px">'+f+'</b><p style="font-size:11px;color:#888">ملف جاهز • VPS</p><a href="/download/'+f+'?user_id='+UID+'">⬇ تحميل</a></div>';});document.getElementById('list').innerHTML=h;}async function loadProto(){let p=await fetch('/api/protocols/'+UID).then(r=>r.json()).catch(()=>null);let box=document.getElementById('proto');if(!p||!p.ok){box.innerHTML='<div class="pcard">VPS غير متصل - جرب بعد شوية</div>';return;}let cfg=p.config;let html='<b>🔐 بروتوكولاتك</b>';function card(t,v){return '<div class="pcard"><button onclick="navigator.clipboard.writeText(`'+v.replace(/`/g,'')+'`);alert(\\'تم النسخ\\')">نسخ</button><b style="font-size:13px">'+t+'</b><p dir="ltr">'+v+'</p></div>';}if(cfg.ssh) html+=card('SSH',cfg.ssh.username+':'+cfg.ssh.password+'@'+cfg.ssh.host+':'+cfg.ssh.port);if(cfg.tls) html+=card('TLS',cfg.tls.host+':'+cfg.tls.port+' SNI:'+cfg.tls.sni);if(cfg.vless) html+=card('VLESS',cfg.vless.link);if(cfg.trojan) html+=card('Trojan',cfg.trojan.link);if(cfg.vmess) html+=card('VMESS',cfg.vmess.link);box.innerHTML=html;}function filterFiles(){let q=(document.getElementById('search').value||'').toLowerCase();document.querySelectorAll('.file-card').forEach(el=>{el.style.display=el.dataset.name.toLowerCase().includes(q)?'block':'none';});}load();</script></body></html>"""

LIBRARY_HTML = CONTENT_HTML
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
def pay_madar_page(user_id): return Response(MADAR_HTML.replace("__UID__", user_id), mimetype='text/html')
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
    app.run(host='0.0.0.0', port=PORT)

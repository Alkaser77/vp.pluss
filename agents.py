# agent.py - كامل - SSH + TLS + VLESS + Trojan + VMESS
# يشتغل في VPS لينكس على بورت 5001
# تشغيل: pip install flask
#        python agent.py
from flask import Flask, request, jsonify
import os, json, time, secrets, threading, random, string, uuid, hashlib, base64, subprocess
from datetime import datetime, timedelta

app = Flask(__name__)

# ===== عدل هنا لما تشري VPS =====
VPS_TOKEN = "vps_libya_2026_8rT9yU2iO5p"  # لازم نفس اللي في app.py
PORT = 5001
VPS_HOST = os.getenv("VPS_HOST", "YOUR_VPS_IP")
DOMAIN = os.getenv("DOMAIN", "").strip() or VPS_HOST  # لو فاضي في Render، يستعمل IP
# =================================

BUNDLES = {}
LOCK = threading.Lock()

HOURS_MAP = {'free': 2, 'paid': 720, '1h': 1, '3h': 3, '6h': 6, '12h': 12, '24h': 24, '7d': 168, '30d': 720}

def check_token():
    return request.headers.get("X-Agent-Token") == VPS_TOKEN

# ===== 1. SSH =====
def create_ssh_user(user_id, hours):
    username = "u" + user_id.replace("user_", "")[-6:]
    # لو الاسم فيه حروف غريبة نظفه
    username = ''.join(c for c in username if c.isalnum())[:10]
    if len(username) < 3: username = "u" + ''.join(random.choices(string.digits, k=6))
    password = secrets.token_hex(4)  # 8 حروف
    expire_date = (datetime.now() + timedelta(hours=hours)).strftime("%Y-%m-%d")
    try:
        # لو يخدم على ويندوز / تجريب بدون root -> يرجع وهمي
        if os.name == 'nt':
            return {"username": username, "password": password, "host": VPS_HOST, "port": 22, "expire": expire_date, "mode": "fake-windows-test"}
        subprocess.run(["userdel", "-r", username], capture_output=True)
        subprocess.run(["useradd", "-M", "-s", "/bin/false", "-e", expire_date, username], check=True)
        subprocess.run(f"echo '{username}:{password}' | chpasswd", shell=True, check=True)
        return {"username": username, "password": password, "host": VPS_HOST, "port": 22, "expire": expire_date, "mode": "real"}
    except Exception as e:
        print(f"SSH fail {username}: {e} -> fake mode")
        return {"username": username, "password": password, "host": VPS_HOST, "port": 22, "expire": expire_date, "mode": "fake-fallback", "error": str(e)}

def delete_ssh_user(user_id):
    username = "u" + user_id.replace("user_", "")[-6:]
    username = ''.join(c for c in username if c.isalnum())[:10]
    try:
        if os.name != 'nt':
            subprocess.run(["userdel", "-r", username], capture_output=True)
    except: pass

# ===== 2. TLS =====
def get_tls_config(user_id):
    return {
        "host": VPS_HOST,
        "port": 443,
        "sni": DOMAIN,
        "domain": DOMAIN,
        "cert_path": "/etc/letsencrypt/live/" + DOMAIN + "/fullchain.pem",
        "key_path": "/etc/letsencrypt/live/" + DOMAIN + "/privkey.pem",
        "note": "ركب شهادة بـ: certbot certonly --standalone -d " + DOMAIN
    }

# ===== 3. VLESS =====
def make_vless(user_id, plan):
    uid = str(uuid.uuid4())
    short = user_id[:12]
    link = f"vless://{uid}@{VPS_HOST}:443?security=reality&sni={DOMAIN}&fp=chrome&type=tcp&flow=xtls-rprx-vision#{short}-{plan}"
    return {"uuid": uid, "host": VPS_HOST, "port": 443, "security": "reality", "sni": DOMAIN, "type": "tcp", "flow": "xtls-rprx-vision", "link": link}

# ===== 4. TROJAN =====
def make_trojan(user_id, plan):
    pwd = secrets.token_hex(8)
    short = user_id[:12]
    link = f"trojan://{pwd}@{VPS_HOST}:443?security=tls&sni={DOMAIN}&type=tcp#{short}-{plan}"
    return {"password": pwd, "host": VPS_HOST, "port": 443, "security": "tls", "sni": DOMAIN, "link": link}

# ===== 5. VMESS =====
def make_vmess(user_id, plan):
    vmess_id = str(uuid.uuid4())
    short = user_id[:12]
    cfg = {
        "v": "2",
        "ps": f"{short}-{plan}",
        "add": VPS_HOST,
        "port": "443",
        "id": vmess_id,
        "aid": "0",
        "scy": "auto",
        "net": "ws",
        "type": "none",
        "host": DOMAIN,
        "path": f"/{vmess_id}",
        "tls": "tls",
        "sni": DOMAIN,
        "alpn": ""
    }
    b64 = base64.b64encode(json.dumps(cfg).encode()).decode()
    link = f"vmess://{b64}"
    return {"id": vmess_id, "host": VPS_HOST, "port": 443, "path": cfg["path"], "tls": "tls", "sni": DOMAIN, "net": "ws", "config": cfg, "link": link}

# ===== تجميع الكل في blob واحد =====
def make_blob(user_id, plan, hours):
    ssh = create_ssh_user(user_id, hours)
    tls = get_tls_config(user_id)
    vless = make_vless(user_id, plan)
    trojan = make_trojan(user_id, plan)
    vmess = make_vmess(user_id, plan)

    full = {
        "user_id": user_id,
        "plan": plan,
        "host": VPS_HOST,
        "domain": DOMAIN,
        "created": int(time.time()),
        "expire_hours": hours,
        "expire_at": (datetime.now() + timedelta(hours=hours)).isoformat(),
        # --- SSH ---
        "ssh": ssh,
        "ssh_string": f"{ssh['username']}:{ssh['password']}@{VPS_HOST}:22" if ssh else None,
        # --- TLS ---
        "tls": tls,
        # --- VLESS ---
        "vless": vless,
        # --- TROJAN ---
        "trojan": trojan,
        # --- VMESS ---
        "vmess": vmess,
        # روابط جاهزة للنسخ في التطبيق
        "all_links": {
            "vless": vless["link"],
            "trojan": trojan["link"],
            "vmess": vmess["link"]
        }
    }
    return json.dumps(full).encode().hex()

def cleanup_loop():
    while True:
        try:
            now = time.time()
            with LOCK:
                dead = [k for k, v in BUNDLES.items() if v["expire"] < now]
                for k in dead:
                    print(f"[CLEANUP] expired {k}")
                    delete_ssh_user(k)
                    del BUNDLES[k]
        except Exception as e:
            print("cleanup error", e)
        time.sleep(60)

# ===== API =====
@app.route('/api/agent/create_bundle', methods=['POST'])
def create_bundle():
    if not check_token(): return jsonify({"error": "unauthorized"}), 401
    data = request.get_json(silent=True) or {}
    user_id = data.get("user_id")
    plan = data.get("plan", "free")
    if not user_id: return jsonify({"error": "user_id required"}), 400
    hours = HOURS_MAP.get(plan, 2)
    expire = time.time() + hours * 3600
    # احذف القديم
    with LOCK:
        if user_id in BUNDLES:
            delete_ssh_user(user_id)
    blob = make_blob(user_id, plan, hours)
    with LOCK:
        BUNDLES[user_id] = {"blob": blob, "plan": plan, "expire": expire, "created": time.time()}
    print(f"[CREATE] {user_id} plan={plan} hours={hours}")
    return jsonify({"ok": True, "user_id": user_id, "plan": plan, "hours": hours, "expire": expire, "blob_len": len(blob)})

@app.route('/api/agent/get_blob', methods=['POST'])
def get_blob():
    if not check_token(): return jsonify({"error": "unauthorized"}), 401
    data = request.get_json(silent=True) or {}
    user_id = data.get("user_id")
    with LOCK:
        b = BUNDLES.get(user_id)
    if not b: return jsonify({"error": "not found"}), 404
    if b["expire"] < time.time():
        with LOCK:
            BUNDLES.pop(user_id, None)
        delete_ssh_user(user_id)
        return jsonify({"error": "expired"}), 410
    return jsonify({"ok": True, "blob": b["blob"], "plan": b["plan"], "expire": b["expire"]})

@app.route('/api/agent/status', methods=['POST'])
def status():
    if not check_token(): return jsonify({"error": "unauthorized"}), 401
    data = request.get_json(silent=True) or {}
    user_id = data.get("user_id")
    with LOCK:
        b = BUNDLES.get(user_id)
    if not b: return jsonify({"exists": False, "user_id": user_id})
    return jsonify({"exists": True, "user_id": user_id, "plan": b["plan"], "expire": b["expire"], "remaining_sec": max(0, int(b["expire"] - time.time()))})

@app.route('/api/agent/delete_bundle', methods=['POST'])
def delete_bundle():
    if not check_token(): return jsonify({"error": "unauthorized"}), 401
    data = request.get_json(silent=True) or {}
    user_id = data.get("user_id")
    with LOCK:
        existed = user_id in BUNDLES
        BUNDLES.pop(user_id, None)
    delete_ssh_user(user_id)
    return jsonify({"ok": True, "deleted": existed})

@app.route('/api/agent/connect', methods=['POST'])
def connect():
    if not check_token(): return jsonify({"error": "unauthorized"}), 401
    data = request.get_json(silent=True) or {}
    blob = data.get("blob")
    if not blob: return jsonify({"error": "blob required"}), 400
    try:
        raw = bytes.fromhex(blob).decode()
        cfg = json.loads(raw)
        return jsonify({
            "ok": True,
            "user_id": cfg.get("user_id"),
            "plan": cfg.get("plan"),
            "host": cfg.get("host"),
            "ssh": cfg.get("ssh"),
            "tls": cfg.get("tls"),
            "vless": cfg.get("vless"),
            "trojan": cfg.get("trojan"),
            "vmess": cfg.get("vmess"),
            "all_links": cfg.get("all_links")
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 400

@app.route('/health')
def health():
    return jsonify({"ok": True, "host": VPS_HOST, "domain": DOMAIN, "bundles": len(BUNDLES), "protocols": ["SSH", "TLS", "VLESS", "Trojan", "VMESS"]})

if __name__ == '__main__':
    threading.Thread(target=cleanup_loop, daemon=True).start()
    print(f"=== VPS AGENT - SSH+TLS+VLESS+Trojan+VMESS ===")
    print(f"Host: {VPS_HOST} - Port: {PORT} - Domain: {DOMAIN}")
    app.run(host='0.0.0.0', port=PORT)

# agent.py - VPS - الجزء 1
# تشغيل: python3 agent.py -> 5001
import json, os, hashlib, uuid, datetime, secrets, subprocess
from flask import Flask, request, jsonify
from cryptography.fernet import Fernet
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

# ======== المفاتيح - جاهزة - انسخها نفسها في app.py ========
ENCRYPT_KEY = b'X7pQ9vK2mN4bV8cZ1xL5aS3dF6gH9jK0lM2nB4vC7xQ='
SECRET = "libya_secret_2026_9XkL2mQ7wE"
VPS_TOKEN = "vps_libya_2026_8rT9yU2iO5p"
VPS_HOST = "1.2.3.4"
DNSTT_DOMAIN = "dns.yourdomain.com"
DNSTT_PUBKEY = "pubkey_dnstt_hna"
DB_FILE = "/opt/vpn/db.json"
XRAY_CONFIG = "/usr/local/etc/xray/config.json"
XRAY_CLIENTS_FILE = "/opt/vpn/xray_clients.json"
# ==============================

def load_db():
    if not os.path.exists(DB_FILE): return {}
    try: return json.load(open(DB_FILE))
    except: return {}
def save_db(db):
    os.makedirs(os.path.dirname(DB_FILE), exist_ok=True)
    json.dump(db, open(DB_FILE,'w'), indent=2)

def run(cmd):
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=15)
        return r.stdout + r.stderr
    except Exception as e:
        return str(e)

def make_ref(user_id, expire):
    raw = f"{user_id}|{expire}|{SECRET}"
    return hashlib.sha256(raw.encode()).hexdigest()[:20]

def check_auth():
    return request.headers.get("X-Agent-Token") == VPS_TOKEN

def time_left(expire_str):
    try:
        exp = datetime.datetime.fromisoformat(expire_str)
        diff = exp - datetime.datetime.now()
        if diff.total_seconds() <= 0: return "0:00:00"
        h = int(diff.total_seconds() // 3600)
        m = int((diff.total_seconds() % 3600) // 60)
        s = int(diff.total_seconds() % 60)
        return f"{h}:{m:02d}:{s:02d}"
    except: return "0:00:00"

# ===== 1. SSH - يوزر لينكس حقيقي =====
def create_ssh_user(username, password):
    run(f"userdel -r {username} 2>/dev/null; useradd -M -s /usr/sbin/nologin {username} 2>/dev/null || useradd -M -s /bin/false {username}")
    run(f"echo '{username}:{password}' | chpasswd")
    return True

def delete_ssh_user(username):
    run(f"userdel -r {username} 2>/dev/null; pkill -u {username} 2>/dev/null; killall -u {username} 2>/dev/null")
    return True

# ===== 2. XRAY =====
def load_xray_clients():
    if not os.path.exists(XRAY_CLIENTS_FILE): return {}
    try: return json.load(open(XRAY_CLIENTS_FILE))
    except: return {}

def save_xray_clients(d):
    os.makedirs(os.path.dirname(XRAY_CLIENTS_FILE), exist_ok=True)
    json.dump(d, open(XRAY_CLIENTS_FILE,'w'), indent=2)

def sync_xray_config():
    clients = load_xray_clients()
    db = load_db()
    active = {}
    for uid, c in clients.items():
        u = db.get(uid)
        if not u: continue
        try:
            if datetime.datetime.now() > datetime.datetime.fromisoformat(u['expire']):
                continue
        except: continue
        if u.get('status') == 'blocked_leak': continue
        active[uid] = c
    vless_clients = []
    vmess_clients = []
    trojan_clients = []
    for uid, c in active.items():
        vless_clients.append({"id": c['vless_uuid'], "email": uid, "flow": "xtls-rprx-vision"})
        vmess_clients.append({"id": c['vmess_uuid'], "email": uid, "alterId": 0})
        trojan_clients.append({"password": c['trojan_pass'], "email": uid})
    config = {
        "log": {"loglevel": "warning"},
        "inbounds": [
            {"port": 10087, "protocol": "vless", "settings": {"clients": vless_clients, "decryption": "none"}, "streamSettings": {"network": "tcp", "security": "reality", "realitySettings": {"dest": "www.google.com:443", "serverNames": ["www.google.com"], "privateKey": "PRIVATE_KEY_XRAY", "shortIds": [""]}}},
            {"port": 10086, "protocol": "vmess", "settings": {"clients": vmess_clients}, "streamSettings": {"network": "ws", "wsSettings": {"path": "/vmess"}}},
            {"port": 10088, "protocol": "trojan", "settings": {"clients": trojan_clients}, "streamSettings": {"network": "tcp", "security": "tls", "tlsSettings": {"certificates": [{"certificateFile": "/etc/ssl/certs/cert.pem", "keyFile": "/etc/ssl/private/key.pem"}]}}},
            {"port": 10089, "protocol": "vless", "settings": {"clients": vless_clients, "decryption": "none"}, "streamSettings": {"network": "ws", "wsSettings": {"path": "/vless"}}}
        ],
        "outbounds": [{"protocol": "freedom", "tag": "direct"}, {"protocol": "blackhole", "tag": "blocked"}]
    }
    os.makedirs(os.path.dirname(XRAY_CONFIG), exist_ok=True)
    json.dump(config, open(XRAY_CONFIG,'w'), indent=2)
    run("systemctl restart xray 2>/dev/null || service xray restart 2>/dev/null")
    return True

def create_xray_user(user_id):
    clients = load_xray_clients()
    vless_uuid = str(uuid.uuid4())
    vmess_uuid = str(uuid.uuid4())
    trojan_pass = secrets.token_hex(8)
    clients[user_id] = {"vless_uuid": vless_uuid, "vmess_uuid": vmess_uuid, "trojan_pass": trojan_pass}
    save_xray_clients(clients)
    sync_xray_config()
    return clients[user_id]

def delete_xray_user(user_id):
    clients = load_xray_clients()
    if user_id in clients:
        del clients[user_id]
        save_xray_clients(clients)
        sync_xray_config()
    return True

# ===== 3. DNSTT =====
def create_dnstt_user(user_id):
    return {"domain": DNSTT_DOMAIN, "pubkey": DNSTT_PUBKEY, "user": user_id}

# ===== 4. انشاء باقة =====
@app.route('/api/agent/create_bundle', methods=['POST'])
def create_bundle():
    if not check_auth(): return jsonify({"error": "unauthorized"}), 401
    data = request.json or {}
    user_id = data.get('user_id') or f"user_{secrets.token_hex(4)}"
    plan = data.get('plan', '1h')
    hours_map = {'1h': 1, '3h': 3, '6h': 6, '12h': 12, '24h': 24, '7d': 168, '30d': 720}
    hours = hours_map.get(plan, 1)
    expire = (datetime.datetime.now() + datetime.timedelta(hours=hours)).isoformat()

    ssh_user = f"u{secrets.token_hex(3)}"
    ssh_pass = secrets.token_urlsafe(10)
    create_ssh_user(ssh_user, ssh_pass)
    xray = create_xray_user(user_id)
    dnstt = create_dnstt_user(user_id)

    info = {
        "ssh": {"host": VPS_HOST, "port": 22, "user": ssh_user, "pass": ssh_pass},
        "vless": {"host": VPS_HOST, "port": 10087, "uuid": xray['vless_uuid'], "sni": "www.google.com", "flow": "xtls-rprx-vision"},
        "vmess": {"host": VPS_HOST, "port": 10086, "uuid": xray['vmess_uuid'], "path": "/vmess"},
        "trojan": {"host": VPS_HOST, "port": 10088, "pass": xray['trojan_pass']},
        "vless_ws": {"host": VPS_HOST, "port": 10089, "uuid": xray['vless_uuid'], "path": "/vless"},
        "dnstt": dnstt,
        "dns": {"host": VPS_HOST, "port": 53}
    }

    ref = make_ref(user_id, expire)
    f = Fernet(ENCRYPT_KEY)
    blob = f.encrypt(json.dumps({"ref": ref, "user_id": user_id}).encode()).decode()

    db = load_db()
    db[user_id] = {"user_id": user_id, "plan": plan, "expire": expire, "ref": ref, "blob": blob, "info": info, "status": "active", "allowed_ip": None}
    save_db(db)
    return jsonify({"user_id": user_id, "plan": plan, "expire": expire, "blob": blob, "info": info, "status": "active", "time_left": time_left(expire)})

# ===== 5. حذف / انتهاء =====
@app.route('/api/agent/delete_bundle', methods=['POST'])
def delete_bundle():
    if not check_auth(): return jsonify({"error": "unauthorized"}), 401
    user_id = (request.json or {}).get('user_id')
    db = load_db()
    u = db.get(user_id)
    if not u: return jsonify({"error": "not found"}), 404
    if 'ssh' in u.get('info', {}): delete_ssh_user(u['info']['ssh']['user'])
    delete_xray_user(user_id)
    u['status'] = 'expired'
    save_db(db)
    return jsonify({"status": "deleted", "user_id": user_id})

@app.route('/api/agent/get_blob', methods=['POST'])
def get_blob():
    if not check_auth(): return jsonify({"error": "unauthorized"}), 401
    user_id = (request.json or {}).get('user_id')
    db = load_db()
    u = db.get(user_id)
    if not u: return jsonify({"error": "not found"}), 404
    if datetime.datetime.now() > datetime.datetime.fromisoformat(u['expire']):
        if 'ssh' in u.get('info', {}): delete_ssh_user(u['info']['ssh']['user'])
        delete_xray_user(user_id)
        u['status'] = 'expired'
        save_db(db)
    return jsonify({"blob": u['blob'], "expire": u['expire'], "plan": u['plan'], "status": u['status'], "time_left": time_left(u['expire'])})

@app.route('/api/agent/connect', methods=['POST'])
def connect():
    data = request.json or {}
    blob = data.get('blob')
    ip = request.headers.get('X-Forwarded-For', request.remote_addr).split(',')[0].strip()
    if not blob: return jsonify({"error": "blob required"}), 400
    f = Fernet(ENCRYPT_KEY)
    try: ref = json.loads(f.decrypt(blob.encode()).decode())['ref']
    except: return jsonify({"error": "blob invalid"}), 403
    db = load_db()
    for uid, u in db.items():
        if u.get('ref') == ref:
            if datetime.datetime.now() > datetime.datetime.fromisoformat(u['expire']):
                if 'ssh' in u.get('info', {}): delete_ssh_user(u['info']['ssh']['user'])
                delete_xray_user(uid)
                u['status'] = 'expired'; save_db(db)
                return jsonify({"error": "expired"}), 403
            if u.get('status') == 'blocked_leak': return jsonify({"error": "blocked_leak"}), 403
            if u.get('allowed_ip') is None:
                u['allowed_ip'] = ip; save_db(db)
            elif u['allowed_ip'] != ip:
                u['status'] = 'blocked_leak'; save_db(db)
                if 'ssh' in u.get('info', {}): delete_ssh_user(u['info']['ssh']['user'])
                delete_xray_user(uid)
                return jsonify({"error": "blocked_leak"}), 403
            return jsonify({"status": "ok", "allow": True, "expire": u['expire'], "time_left": time_left(u['expire']), "plan": u['plan']})
    return jsonify({"error": "not found"}), 404

@app.route('/api/agent/status', methods=['POST'])
def status():
    if not check_auth(): return jsonify({"error": "unauthorized"}), 401
    user_id = (request.json or {}).get('user_id')
    db = load_db()
    u = db.get(user_id)
    if not u: return jsonify({"error": "not found"}), 404
    if datetime.datetime.now() > datetime.datetime.fromisoformat(u['expire']):
        u['status'] = 'expired'; save_db(db)
    return jsonify({"user_id": user_id, "plan": u['plan'], "expire": u['expire'], "status": u['status'], "time_left": time_left(u['expire'])})

if __name__ == '__main__':
    print("Agent running 5001 - ALL SERVICES REAL")
    app.run(host='0.0.0.0', port=5001)


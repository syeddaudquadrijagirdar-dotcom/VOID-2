from flask import Flask, render_template_string, jsonify, request, session, redirect, url_for
import requests
import secrets
import string
import re
from datetime import datetime, timedelta
import time
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps

app = Flask(__name__)
app.secret_key = secrets.token_hex(32)
app.permanent_session_lifetime = timedelta(days=7)

# ===== EMAIL SENDING CONFIGURATION =====
SMTP_CONFIG = {
    'enabled': False,
    'host': 'smtp.gmail.com',
    'port': 587,
    'username': 'your_email@gmail.com',
    'password': 'your_app_password',
    'use_tls': True
}

def send_real_email(to_email, subject, body, from_email):
    if SMTP_CONFIG['enabled'] and SMTP_CONFIG['username'] != 'your_email@gmail.com':
        try:
            msg = MIMEMultipart()
            msg['From'] = from_email
            msg['To'] = to_email
            msg['Subject'] = subject
            msg.attach(MIMEText(body, 'plain'))
            server = smtplib.SMTP(SMTP_CONFIG['host'], SMTP_CONFIG['port'])
            if SMTP_CONFIG['use_tls']:
                server.starttls()
            server.login(SMTP_CONFIG['username'], SMTP_CONFIG['password'])
            server.send_message(msg)
            server.quit()
            return True, "✅ Email sent!"
        except Exception as e:
            return False, str(e)
    print(f"\n📧 DEMO: To: {to_email} | Subject: {subject}\n")
    return False, "Demo mode"

SPAM_KEYWORDS = [
    'winner', 'congratulations', 'prize', 'lottery', 'free money', 'click here',
    'urgent', 'limited time', 'act now', 'earn money', 'work from home',
    'million dollars', 'verify your account', 'crypto', 'bitcoin'
]

def analyze_spam(subject, from_address, text_content):
    score = 0
    flags = []
    combined = ((subject or '') + ' ' + (text_content or '')).lower()
    keyword_hits = [kw for kw in SPAM_KEYWORDS if kw in combined]
    if keyword_hits:
        score += min(len(keyword_hits) * 15, 60)
        flags.append(f"Spam: {', '.join(keyword_hits[:3])}")
    if score >= 60: level = "HIGH"
    elif score >= 30: level = "MEDIUM"
    elif score >= 10: level = "LOW"
    else: level = "CLEAN"
    return {"score": min(score, 100), "level": level, "flags": flags[:4]}

# ===== MULTI-USER SYSTEM =====
USERS = {}          # username (lowercase) -> {password, created_at}
USER_TEMP_DATA = {} # username (lowercase) -> {token, email, seq, expiry}

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'username' not in session:
            return jsonify({"error": "Unauthorized"}), 401
        return f(*args, **kwargs)
    return decorated_function

# ===== LOGIN/REGISTER ROUTES =====
@app.route('/')
def index():
    if 'username' in session:
        return render_template_string(MAIN_HTML_TEMPLATE, username=session['username'])
    return render_template_string(LOGIN_HTML_TEMPLATE)

@app.route('/login', methods=['POST'])
def login():
    data = request.json
    username = data.get('username', '').strip().lower()   # case-insensitive
    password = data.get('password', '')
    
    if username not in USERS:
        return jsonify({"success": False, "error": "User not found"}), 401
    
    if check_password_hash(USERS[username]['password'], password):
        session['username'] = username
        session.permanent = True
        return jsonify({"success": True, "redirect": "/"})
    else:
        return jsonify({"success": False, "error": "Invalid password"}), 401

@app.route('/register', methods=['POST'])
def register():
    data = request.json
    username = data.get('username', '').strip().lower()   # store lowercase
    password = data.get('password', '')
    
    # Username validation
    if not username or len(username) < 3 or len(username) > 20:
        return jsonify({"success": False, "error": "Username must be 3-20 characters"}), 400
    if not re.match(r'^[a-zA-Z0-9_-]+$', username):
        return jsonify({"success": False, "error": "Username can only contain letters, numbers, underscore, hyphen"}), 400
    
    # Password validation
    if len(password) < 8:
        return jsonify({"success": False, "error": "Password must be at least 8 characters"}), 400
    if not re.search(r'[!@#$%^&*(),.?":{}|<>]', password):
        return jsonify({"success": False, "error": "Password must contain at least one special character"}), 400
    if len(re.findall(r'\d', password)) < 3:
        return jsonify({"success": False, "error": "Password must contain at least 3 numbers"}), 400
    
    if username in USERS:
        return jsonify({"success": False, "error": "Username already exists"}), 400
    
    USERS[username] = {
        'password': generate_password_hash(password),
        'created_at': datetime.now()
    }
    
    # ✅ FIX 1: Auto-login after registration
    session['username'] = username
    session.permanent = True
    
    return jsonify({"success": True, "redirect": "/"})

@app.route('/logout')
def logout():
    if 'username' in session:
        USER_TEMP_DATA.pop(session['username'], None)
    session.clear()
    return redirect('/')

# ===== API ENDPOINTS =====
GUERRILLA_API = "https://api.guerrillamail.com/ajax.php"

@app.route('/api/user_state')
@login_required
def user_state():
    username = session['username']
    if username in USER_TEMP_DATA:
        data = USER_TEMP_DATA[username]
        return jsonify({
            'has_email': True,
            'email': data['email'],
            'token': data['token'],
            'expiry': data['expiry']
        })
    return jsonify({'has_email': False})

@app.route('/api/create_account', methods=['POST'])
@login_required
def create_account():
    username = session['username']
    try:
        data = request.json
        custom_username = data.get('custom_username', '').strip()
        selected_domain = data.get('selected_domain', '@guerrillamailblock.com')
        
        allowed_domains = [
            '@guerrillamailblock.com',
            '@guerrillamail.com', 
            '@guerrillamail.net',
            '@sharklasers.com'
        ]
        if selected_domain not in allowed_domains:
            selected_domain = '@guerrillamailblock.com'
        
        if custom_username and re.match(r'^[a-zA-Z0-9_-]+$', custom_username):
            if len(custom_username) < 3 or len(custom_username) > 20:
                return jsonify({"error": "Username 3-20 characters"}), 400
            user = custom_username.lower()
        else:
            user = ''.join(secrets.choice(string.ascii_lowercase + string.digits) for _ in range(10))
        
        r1 = requests.get(GUERRILLA_API, params={'f': 'get_email_address', 'lang': 'en'}, timeout=10)
        if r1.status_code != 200:
            return jsonify({"error": "Server unavailable"}), 503
        init = r1.json()
        sid_token = init.get('sid_token', '')
        
        r2 = requests.get(GUERRILLA_API, params={
            'f': 'set_email_user',
            'email_user': user,
            'lang': 'en',
            'sid_token': sid_token
        }, timeout=10)
        set_data = r2.json()
        base_address = set_data.get('email_addr', '')
        if not base_address:
            return jsonify({"error": "Could not generate"}), 500
        local_part = base_address.split('@')[0]
        address = f"{local_part}{selected_domain}"
        sid_token = set_data.get('sid_token', sid_token)
        
        USER_TEMP_DATA[username] = {
            'token': sid_token,
            'email': address,
            'seq': '0',
            'expiry': time.time() + 86400
        }
        
        return jsonify({
            "address": address,
            "token": sid_token,
            "seq": "0",
            "username": local_part,
            "domain": selected_domain
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/generate_qr')
@login_required
def generate_qr():
    email = request.args.get('email', '')
    if not email:
        return jsonify({"error": "No email"}), 400
    qr_url = f"https://api.qrserver.com/v1/create-qr-code/?size=200x200&data=mailto:{email}"
    return jsonify({"qr_code": qr_url})

@app.route('/api/get_messages')
@login_required
def get_messages():
    username = session['username']
    if username not in USER_TEMP_DATA:
        return jsonify([]), 200
    
    user_data = USER_TEMP_DATA[username]
    sid_token = user_data['token']
    seq = user_data.get('seq', '0')
    
    try:
        r = requests.get(GUERRILLA_API, params={
            'f': 'check_email',
            'seq': seq,
            'sid_token': sid_token
        }, timeout=5)
        if r.status_code != 200:
            return jsonify([]), r.status_code
        resp = r.json()
        raw_list = resp.get('list', [])
        if 'seq' in resp:
            USER_TEMP_DATA[username]['seq'] = resp['seq']
        
        msgs = []
        for m in raw_list:
            if str(m.get('mail_id', '0')) == '0':
                continue
            normalized = {
                'id': str(m.get('mail_id', '')),
                'subject': m.get('mail_subject', '(no subject)'),
                'from': {'address': m.get('mail_from', 'unknown')},
                'createdAt': m.get('mail_date', ''),
                'intro': m.get('mail_excerpt', ''),
            }
            normalized['_spam'] = analyze_spam(
                subject=normalized['subject'],
                from_address=normalized['from']['address'],
                text_content=normalized['intro']
            )
            msgs.append(normalized)
        return jsonify(msgs)
    except Exception as e:
        return jsonify([]), 500

@app.route('/api/get_message/<path:msg_id>')
@login_required
def get_message(msg_id):
    username = session['username']
    if username not in USER_TEMP_DATA:
        return jsonify({"error": "No active inbox"}), 401
    
    sid_token = USER_TEMP_DATA[username]['token']
    try:
        r = requests.get(GUERRILLA_API, params={
            'f': 'fetch_email',
            'email_id': msg_id,
            'sid_token': sid_token
        }, timeout=10)
        raw = r.json()
        body = raw.get('mail_body', '')
        is_html = bool(re.search(r'<[a-zA-Z]', body))
        msg = {
            'id': str(raw.get('mail_id', msg_id)),
            'subject': raw.get('mail_subject', '(no subject)'),
            'from': {'address': raw.get('mail_from', 'unknown')},
            'createdAt': raw.get('mail_date', ''),
            'html': [body] if is_html else [],
            'text': body if not is_html else '',
        }
        msg['_spam'] = analyze_spam(
            subject=msg['subject'],
            from_address=msg['from']['address'],
            text_content=body + ' ' + msg['subject']
        )
        return jsonify(msg)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/send_reply', methods=['POST'])
@login_required
def send_reply():
    username = session['username']
    if username not in USER_TEMP_DATA:
        return jsonify({"error": "No active inbox"}), 400
    
    try:
        data = request.json
        to_address = data.get('to')
        subject = data.get('subject', 'Re: (no subject)')
        text_body = data.get('text')
        from_address = USER_TEMP_DATA[username]['email']
        
        if not to_address or not text_body:
            return jsonify({"error": "Missing fields"}), 400
        success, message = send_real_email(to_address, subject, text_body, from_address)
        return jsonify({"success": success, "message": message, "delivered": success})
    except Exception as e:
        return jsonify({"error": str(e), "success": False}), 500

# ===== LOGIN/REGISTER HTML (unchanged) =====
LOGIN_HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en" data-theme="dark">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>VoidMail — Login / Register</title>
    <link href="https://fonts.googleapis.com/css2?family=Syne:wght@400;600;700;800&family=JetBrains+Mono:ital,wght@0,300;0,400;0,500;1,300&display=swap" rel="stylesheet">
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        :root {
            --bg-deep: #04060e;
            --bg-card: #111826;
            --cyan: #00f0ff;
            --violet: #8b5cf6;
            --magenta: #ff2d78;
            --text-primary: #e4ecf7;
            --text-secondary: #6b7a96;
            --border: rgba(255,255,255,0.06);
        }
        [data-theme="light"] {
            --bg-deep: #f0f2f8;
            --bg-card: #ffffff;
            --text-primary: #1a1a2e;
            --border: rgba(0,0,0,0.08);
            --cyan: #0066cc;
        }
        body {
            font-family: 'Syne', sans-serif;
            background: var(--bg-deep);
            color: var(--text-primary);
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
        }
        .login-container {
            background: var(--bg-card);
            border: 1px solid var(--border);
            border-radius: 24px;
            padding: 40px;
            width: 420px;
            max-width: 90%;
            box-shadow: 0 20px 40px rgba(0,0,0,0.3);
        }
        .logo {
            text-align: center;
            font-size: 28px;
            font-weight: 800;
            margin-bottom: 30px;
        }
        .logo em { color: var(--cyan); font-style: normal; }
        .tabs {
            display: flex;
            gap: 20px;
            margin-bottom: 30px;
            border-bottom: 1px solid var(--border);
        }
        .tab {
            padding: 10px 0;
            cursor: pointer;
            font-weight: 600;
            color: var(--text-secondary);
            transition: all 0.2s;
        }
        .tab.active {
            color: var(--cyan);
            border-bottom: 2px solid var(--cyan);
        }
        .form {
            display: flex;
            flex-direction: column;
            gap: 20px;
        }
        .form-group {
            display: flex;
            flex-direction: column;
            gap: 8px;
        }
        label {
            font-family: 'JetBrains Mono', monospace;
            font-size: 11px;
            letter-spacing: 2px;
            text-transform: uppercase;
            color: var(--text-secondary);
        }
        input {
            background: rgba(255,255,255,0.05);
            border: 1px solid var(--border);
            border-radius: 12px;
            padding: 14px 16px;
            font-family: 'JetBrains Mono', monospace;
            font-size: 14px;
            color: var(--text-primary);
            outline: none;
            transition: all 0.2s;
        }
        input:focus {
            border-color: var(--cyan);
            box-shadow: 0 0 0 2px rgba(0,240,255,0.1);
        }
        button {
            background: linear-gradient(135deg, var(--cyan), var(--violet));
            border: none;
            border-radius: 12px;
            padding: 14px;
            font-family: 'Syne', sans-serif;
            font-weight: 700;
            font-size: 14px;
            color: white;
            cursor: pointer;
            transition: transform 0.2s;
        }
        button:hover { transform: translateY(-2px); }
        .error-msg {
            color: #ff4455;
            font-size: 12px;
            margin-top: 5px;
        }
        .note {
            text-align: center;
            font-size: 11px;
            color: var(--text-secondary);
            margin-top: 20px;
        }
        .toggle-theme {
            position: fixed;
            top: 20px;
            right: 20px;
            background: var(--bg-card);
            border: 1px solid var(--border);
            border-radius: 30px;
            padding: 8px 16px;
            cursor: pointer;
            font-size: 12px;
        }
    </style>
</head>
<body>
<div class="toggle-theme" onclick="toggleTheme()">🌓 Theme</div>
<div class="login-container">
    <div class="logo">Void<em>Mail</em></div>
    <div class="tabs">
        <div class="tab active" data-tab="login">LOGIN</div>
        <div class="tab" data-tab="register">REGISTER</div>
    </div>
    
    <div id="login-form" class="form">
        <div class="form-group">
            <label>Username</label>
            <input type="text" id="login-username" placeholder="your_username">
        </div>
        <div class="form-group">
            <label>Password</label>
            <input type="password" id="login-password" placeholder="••••••••">
        </div>
        <div id="login-error" class="error-msg"></div>
        <button onclick="handleLogin()">→ Login</button>
    </div>
    
    <div id="register-form" class="form" style="display:none;">
        <div class="form-group">
            <label>Username (3-20 chars, letters/numbers/_-)</label>
            <input type="text" id="reg-username" placeholder="cool_user123">
        </div>
        <div class="form-group">
            <label>Password (min 8 chars, 1 special, 3 numbers)</label>
            <input type="password" id="reg-password" placeholder="••••••••">
        </div>
        <div id="register-error" class="error-msg"></div>
        <button onclick="handleRegister()">→ Create Account</button>
    </div>
    <div class="note">⚡ Free • Anonymous • No tracking</div>
</div>

<script>
function toggleTheme() {
    const html = document.documentElement;
    const current = html.getAttribute('data-theme');
    html.setAttribute('data-theme', current === 'dark' ? 'light' : 'dark');
    localStorage.setItem('theme', current === 'dark' ? 'light' : 'dark');
}
const savedTheme = localStorage.getItem('theme');
if (savedTheme) document.documentElement.setAttribute('data-theme', savedTheme);

document.querySelectorAll('.tab').forEach(tab => {
    tab.addEventListener('click', () => {
        document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
        tab.classList.add('active');
        const form = tab.dataset.tab;
        document.getElementById('login-form').style.display = form === 'login' ? 'flex' : 'none';
        document.getElementById('register-form').style.display = form === 'register' ? 'flex' : 'none';
    });
});

async function handleLogin() {
    const username = document.getElementById('login-username').value.trim();
    const password = document.getElementById('login-password').value;
    const errorDiv = document.getElementById('login-error');
    if (!username || !password) {
        errorDiv.textContent = 'Please fill all fields';
        return;
    }
    try {
        const res = await fetch('/login', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username, password })
        });
        const data = await res.json();
        if (data.success) {
            window.location.href = data.redirect;
        } else {
            errorDiv.textContent = data.error || 'Login failed';
        }
    } catch(e) {
        errorDiv.textContent = 'Network error';
    }
}

async function handleRegister() {
    const username = document.getElementById('reg-username').value.trim();
    const password = document.getElementById('reg-password').value;
    const errorDiv = document.getElementById('register-error');
    if (!username || !password) {
        errorDiv.textContent = 'Please fill all fields';
        return;
    }
    try {
        const res = await fetch('/register', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username, password })
        });
        const data = await res.json();
        if (data.success) {
            window.location.href = data.redirect;
        } else {
            errorDiv.textContent = data.error || 'Registration failed';
        }
    } catch(e) {
        errorDiv.textContent = 'Network error';
    }
}
</script>
</body>
</html>
"""

# ===== MAIN INBOX HTML (with English FAQ fix) =====
MAIN_HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en" data-theme="dark">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>VoidMail — Fresh Inbox Every Time</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link href="https://fonts.googleapis.com/css2?family=Syne:wght@400;600;700;800&family=JetBrains+Mono:ital,wght@0,300;0,400;0,500;1,300&display=swap" rel="stylesheet">
    <style>
        *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

        :root {
            --bg-deep: #04060e;
            --bg-mid: #080c18;
            --bg-surface: #0e1320;
            --bg-card: #111826;
            --bg-glass: rgba(255,255,255,0.035);
            --bg-glass-hover: rgba(255,255,255,0.065);
            --border: rgba(255,255,255,0.06);
            --border-bright: rgba(0,240,255,0.3);
            --cyan: #00f0ff;
            --cyan-dim: rgba(0,240,255,0.1);
            --cyan-glow: rgba(0,240,255,0.4);
            --violet: #8b5cf6;
            --violet-dim: rgba(139,92,246,0.15);
            --magenta: #ff2d78;
            --magenta-dim: rgba(255,45,120,0.12);
            --green: #00ff88;
            --green-dim: rgba(0,255,136,0.1);
            --amber: #ffaa00;
            --amber-dim: rgba(255,170,0,0.12);
            --red: #ff4455;
            --red-dim: rgba(255,68,85,0.12);
            --text-primary: #e4ecf7;
            --text-secondary: #6b7a96;
            --text-dim: #2e3a52;
            --radius-sm: 8px;
            --radius: 14px;
            --radius-lg: 18px;
            --radius-xl: 24px;
        }

        [data-theme="light"] {
            --bg-deep: #f0f2f8;
            --bg-card: #ffffff;
            --bg-glass: rgba(0,0,0,0.02);
            --border: rgba(0,0,0,0.08);
            --cyan: #0066cc;
            --violet: #6b4ce6;
            --magenta: #cc2266;
            --green: #00aa55;
            --red: #cc3344;
            --text-primary: #1a1a2e;
            --text-secondary: #555566;
        }

        html { scroll-behavior: smooth; }
        body {
            font-family: 'Syne', sans-serif;
            background: var(--bg-deep);
            color: var(--text-primary);
            min-height: 100vh;
            overflow-x: hidden;
            transition: all 0.3s;
        }

        .bg-canvas {
            position: fixed;
            inset: 0;
            pointer-events: none;
            z-index: 0;
            overflow: hidden;
        }
        .orb {
            position: absolute;
            border-radius: 50%;
            filter: blur(130px);
        }
        [data-theme="dark"] .orb-1 { width: 700px; height: 700px; background: radial-gradient(circle, rgba(0,240,255,0.14) 0%, transparent 70%); top: -300px; left: -200px; animation: drift1 20s ease-in-out infinite; }
        [data-theme="dark"] .orb-2 { width: 600px; height: 600px; background: radial-gradient(circle, rgba(255,45,120,0.1) 0%, transparent 70%); bottom: -250px; right: -200px; animation: drift2 25s ease-in-out infinite; }
        [data-theme="dark"] .orb-3 { width: 450px; height: 450px; background: radial-gradient(circle, rgba(139,92,246,0.12) 0%, transparent 70%); top: 45%; left: 45%; transform: translate(-50%,-50%); animation: drift3 18s ease-in-out infinite; }
        [data-theme="light"] .orb { display: none; }

        @keyframes drift1 { 0%,100%{transform:translate(0,0)} 50%{transform:translate(70px,50px)} }
        @keyframes drift2 { 0%,100%{transform:translate(0,0)} 50%{transform:translate(-60px,-40px)} }
        @keyframes drift3 { 0%,100%{transform:translate(-50%,-50%)} 50%{transform:translate(-42%,-58%)} }

        .wrap { position: relative; z-index: 1; }

        nav {
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: 0 36px;
            height: 62px;
            border-bottom: 1px solid var(--border);
            background: rgba(4,6,14,0.9);
            backdrop-filter: blur(28px);
            position: sticky;
            top: 0;
            z-index: 200;
        }
        [data-theme="light"] nav { background: rgba(255,255,255,0.9); }
        .logo {
            display: flex;
            align-items: center;
            gap: 11px;
            font-size: 20px;
            font-weight: 800;
            letter-spacing: -0.5px;
            text-decoration: none;
        }
        .logo-icon {
            width: 34px;
            height: 34px;
            background: linear-gradient(135deg, var(--cyan), var(--violet));
            border-radius: 9px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 16px;
            box-shadow: 0 0 24px var(--cyan-glow);
            animation: logo-pulse 4s ease-in-out infinite;
        }
        @keyframes logo-pulse {
            0%,100% { box-shadow: 0 0 24px var(--cyan-glow); }
            50% { box-shadow: 0 0 40px var(--cyan-glow), 0 0 60px rgba(139,92,246,0.3); }
        }
        .logo-text { color: var(--text-primary); }
        .logo-text em { color: var(--cyan); font-style: normal; }

        .nav-right { display: flex; align-items: center; gap: 10px; }
        .nav-pill {
            background: var(--bg-glass);
            border: 1px solid var(--border);
            border-radius: 20px;
            padding: 5px 13px;
            font-size: 11px;
            font-weight: 600;
            color: var(--text-secondary);
            font-family: 'JetBrains Mono', monospace;
            display: flex;
            align-items: center;
            gap: 6px;
            cursor: pointer;
            transition: all 0.2s;
        }
        .nav-pill:hover { border-color: var(--border-bright); color: var(--cyan); }
        .status-dot {
            width: 6px;
            height: 6px;
            background: var(--green);
            border-radius: 50%;
            box-shadow: 0 0 8px var(--green);
            animation: blink 2s ease-in-out infinite;
        }
        @keyframes blink { 0%,100%{opacity:1} 50%{opacity:0.3} }

        .ticker {
            background: linear-gradient(90deg, transparent, rgba(0,240,255,0.05), transparent);
            border-bottom: 1px solid rgba(0,240,255,0.08);
            padding: 8px 0;
            overflow: hidden;
        }
        [data-theme="light"] .ticker { background: linear-gradient(90deg, transparent, rgba(0,102,204,0.05), transparent); }
        .ticker-track {
            display: flex;
            gap: 64px;
            animation: scroll-ticker 22s linear infinite;
            width: max-content;
        }
        .t-item {
            font-family: 'JetBrains Mono', monospace;
            font-size: 10px;
            color: rgba(0,240,255,0.5);
            white-space: nowrap;
            letter-spacing: 2px;
            display: flex;
            align-items: center;
            gap: 10px;
        }
        [data-theme="light"] .t-item { color: rgba(0,102,204,0.5); }
        .t-item::before { content: '▸'; opacity: 0.5; }
        @keyframes scroll-ticker { from{transform:translateX(0)} to{transform:translateX(-50%)} }

        .hero {
            text-align: center;
            padding: 64px 20px 52px;
        }
        .hero-tag {
            font-family: 'JetBrains Mono', monospace;
            font-size: 10px;
            letter-spacing: 4px;
            text-transform: uppercase;
            color: var(--cyan);
            margin-bottom: 18px;
            opacity: 0;
            animation: rise 0.7s ease forwards 0.1s;
            display: inline-flex;
            align-items: center;
            gap: 8px;
        }
        .hero-tag::before, .hero-tag::after { content: '//'; opacity: 0.4; }
        .hero h1 {
            font-size: clamp(38px, 6.5vw, 68px);
            font-weight: 800;
            line-height: 1.03;
            letter-spacing: -2.5px;
            margin-bottom: 16px;
            opacity: 0;
            animation: rise 0.7s ease forwards 0.2s;
        }
        .g-text {
            background: linear-gradient(135deg, var(--cyan) 0%, var(--violet) 50%, var(--magenta) 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
        }
        .hero-sub {
            font-size: 15px;
            color: var(--text-secondary);
            max-width: 460px;
            margin: 0 auto 36px;
            line-height: 1.75;
            font-weight: 400;
            opacity: 0;
            animation: rise 0.7s ease forwards 0.35s;
        }
        @keyframes rise { from{opacity:0;transform:translateY(22px)} to{opacity:1;transform:translateY(0)} }

        .ebar-wrap {
            max-width: 860px;
            margin: 0 auto;
            opacity: 0;
            animation: rise 0.7s ease forwards 0.5s;
        }
        .custom-options {
            display: flex;
            gap: 12px;
            margin-bottom: 15px;
            flex-wrap: wrap;
        }
        .username-input {
            flex: 2;
            background: var(--bg-glass);
            border: 1px solid var(--border);
            border-radius: var(--radius-sm);
            padding: 12px 15px;
            font-family: 'JetBrains Mono', monospace;
            font-size: 13px;
            color: var(--text-primary);
            outline: none;
        }
        .username-input:focus { border-color: var(--cyan); }
        .domain-select {
            flex: 1;
            background: var(--bg-glass);
            border: 1px solid var(--border);
            border-radius: var(--radius-sm);
            padding: 12px 15px;
            font-family: 'JetBrains Mono', monospace;
            font-size: 13px;
            color: var(--text-primary);
            cursor: pointer;
        }
        .domain-select:focus { border-color: var(--cyan); }
        
        .ebar {
            background: var(--bg-card);
            border: 1px solid var(--border);
            border-radius: var(--radius-xl);
            padding: 15px 20px;
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 15px;
            transition: border-color 0.35s, box-shadow 0.35s;
            flex-wrap: wrap;
        }
        .ebar.live {
            border-color: rgba(0,240,255,0.28);
            box-shadow: 0 0 0 1px rgba(0,240,255,0.1), 0 0 50px rgba(0,240,255,0.08);
        }
        .ebar-info { flex: 1; min-width: 200px; }
        .ebar-lbl {
            font-family: 'JetBrains Mono', monospace;
            font-size: 9px;
            letter-spacing: 2.5px;
            text-transform: uppercase;
            color: var(--text-dim);
            margin-bottom: 6px;
        }
        #email-addr {
            font-family: 'JetBrains Mono', monospace;
            font-size: 15px;
            font-weight: 500;
            color: var(--cyan);
            word-break: break-all;
        }
        #email-addr.empty { color: var(--text-dim); font-style: italic; }
        .expiry-row {
            display: flex;
            align-items: center;
            gap: 8px;
            margin-top: 8px;
        }
        .expiry-bar-bg {
            flex: 1;
            height: 3px;
            background: var(--bg-glass);
            border-radius: 2px;
            overflow: hidden;
        }
        .expiry-bar-fill {
            height: 100%;
            border-radius: 2px;
            background: linear-gradient(90deg, var(--cyan), var(--violet));
            transition: width 1s linear;
            width: 100%;
        }
        .expiry-time {
            font-family: 'JetBrains Mono', monospace;
            font-size: 10px;
            color: var(--text-secondary);
            white-space: nowrap;
        }
        .ebar-btns {
            display: flex;
            align-items: center;
            gap: 8px;
            flex-wrap: wrap;
        }
        .ic-btn {
            width: 38px;
            height: 38px;
            border: 1px solid var(--border);
            background: var(--bg-glass);
            border-radius: var(--radius-sm);
            display: flex;
            align-items: center;
            justify-content: center;
            cursor: pointer;
            color: var(--text-secondary);
            transition: all 0.2s;
            font-size: 16px;
        }
        .ic-btn:hover:not(:disabled) { border-color: var(--border-bright); color: var(--cyan); background: var(--cyan-dim); }
        .ic-btn:disabled { opacity: 0.3; cursor: default; }
        .btn-gen {
            background: linear-gradient(135deg, var(--cyan) 0%, var(--violet) 100%);
            color: #fff;
            border: none;
            border-radius: var(--radius-sm);
            padding: 0 20px;
            height: 42px;
            font-family: 'Syne', sans-serif;
            font-size: 13px;
            font-weight: 700;
            cursor: pointer;
            display: flex;
            align-items: center;
            gap: 8px;
            transition: all 0.2s;
            white-space: nowrap;
        }
        .btn-gen:hover:not(:disabled) { transform: translateY(-2px); filter: brightness(1.05); }
        .btn-gen:disabled { opacity: 0.5; cursor: default; }
        .btn-del {
            background: var(--magenta-dim);
            color: var(--magenta);
            border: 1px solid rgba(255,45,120,0.2);
            border-radius: var(--radius-sm);
            padding: 0 16px;
            height: 42px;
            font-family: 'Syne', sans-serif;
            font-size: 13px;
            font-weight: 700;
            cursor: pointer;
            display: flex;
            align-items: center;
            gap: 6px;
        }
        .btn-del:hover:not(:disabled) { background: rgba(255,45,120,0.2); }

        .main-grid {
            display: grid;
            grid-template-columns: 380px 1fr;
            gap: 20px;
            max-width: 1300px;
            margin: 0 auto;
            padding: 30px 24px 60px;
        }
        @media(max-width: 860px) { .main-grid { grid-template-columns: 1fr; } }

        .panel {
            background: var(--bg-card);
            border: 1px solid var(--border);
            border-radius: var(--radius-lg);
            overflow: hidden;
            display: flex;
            flex-direction: column;
        }
        .panel-hd {
            padding: 16px 20px;
            border-bottom: 1px solid var(--border);
            display: flex;
            align-items: center;
            justify-content: space-between;
        }
        .badge {
            font-family: 'JetBrains Mono', monospace;
            font-size: 11px;
            background: var(--cyan-dim);
            color: var(--cyan);
            padding: 4px 12px;
            border-radius: 20px;
        }
        .bulk-controls {
            padding: 12px 20px;
            border-bottom: 1px solid var(--border);
            display: flex;
            gap: 12px;
            flex-wrap: wrap;
            background: var(--bg-glass);
        }
        .bulk-btn {
            background: var(--violet-dim);
            color: var(--violet);
            border: 1px solid rgba(139,92,246,0.3);
            border-radius: var(--radius-sm);
            padding: 6px 14px;
            font-size: 11px;
            font-family: 'JetBrains Mono', monospace;
            cursor: pointer;
            transition: all 0.2s;
        }
        .bulk-btn:hover {
            background: var(--violet);
            color: white;
        }
        .delete-selected-btn {
            background: var(--red-dim);
            color: var(--red);
            border: 1px solid rgba(255,68,85,0.3);
            padding: 6px 14px;
            border-radius: var(--radius-sm);
            font-size: 11px;
            cursor: pointer;
            transition: all 0.2s;
        }
        .delete-selected-btn:hover:not(:disabled) {
            background: var(--red);
            color: white;
        }
        .delete-selected-btn:disabled { opacity: 0.4; cursor: not-allowed; }

        .mail-list {
            flex: 1;
            overflow-y: auto;
            min-height: 450px;
            max-height: 550px;
        }
        .mail-item {
            padding: 14px 20px;
            border-bottom: 1px solid var(--border);
            cursor: pointer;
            transition: all 0.15s;
            display: flex;
            gap: 12px;
            align-items: flex-start;
        }
        .mail-item:hover { background: var(--bg-glass-hover); }
        .mail-item.active { background: var(--cyan-dim); border-left: 3px solid var(--cyan); }
        .mail-checkbox { margin-top: 2px; }
        .mail-checkbox input {
            width: 16px;
            height: 16px;
            cursor: pointer;
            accent-color: var(--cyan);
        }
        .mail-content { flex: 1; }
        .mail-from { font-size: 13px; font-weight: 700; margin-bottom: 5px; }
        .mail-subject { font-size: 11px; color: var(--text-secondary); font-family: 'JetBrains Mono', monospace; }
        .mail-time { font-size: 9px; color: var(--text-dim); margin-top: 5px; }
        .spam-badge {
            font-size: 9px;
            padding: 2px 8px;
            border-radius: 12px;
            flex-shrink: 0;
        }
        .spam-CLEAN { background: var(--green-dim); color: var(--green); }
        .spam-LOW { background: var(--amber-dim); color: var(--amber); }
        .spam-MEDIUM { background: rgba(255,100,0,0.15); color: #ff6400; }
        .spam-HIGH { background: var(--red-dim); color: var(--red); }

        .viewer-empty {
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            height: 100%;
            min-height: 550px;
            gap: 14px;
        }
        .viewer-empty-ico { font-size: 52px; opacity: 0.2; }
        .viewer-empty-txt { font-size: 13px; color: var(--text-dim); }
        .viewer-hd {
            padding: 20px 24px;
            border-bottom: 1px solid var(--border);
        }
        .viewer-subject {
            font-size: 18px;
            font-weight: 700;
            margin-bottom: 12px;
        }
        .viewer-meta {
            font-family: 'JetBrains Mono', monospace;
            font-size: 11px;
            color: var(--text-secondary);
            display: flex;
            flex-wrap: wrap;
            gap: 16px;
        }
        .reply-section {
            border-top: 1px solid var(--border);
            padding: 20px 24px;
        }
        .reply-toggle {
            display: flex;
            justify-content: space-between;
            cursor: pointer;
            padding: 8px 0;
        }
        .reply-toggle-ttl {
            font-family: 'JetBrains Mono', monospace;
            font-size: 11px;
            letter-spacing: 2px;
            text-transform: uppercase;
            color: var(--text-dim);
        }
        .reply-body {
            max-height: 0;
            overflow: hidden;
            transition: max-height 0.35s ease;
        }
        .reply-section.open .reply-body { max-height: 500px; }
        .reply-inner { padding-top: 16px; }
        .reply-anon-note {
            background: var(--violet-dim);
            border: 1px solid rgba(139,92,246,0.2);
            border-radius: var(--radius-sm);
            padding: 12px 16px;
            margin-bottom: 16px;
            font-family: 'JetBrains Mono', monospace;
            font-size: 11px;
            color: var(--violet);
        }
        .reply-field-lbl {
            font-family: 'JetBrains Mono', monospace;
            font-size: 9px;
            letter-spacing: 2px;
            text-transform: uppercase;
            color: var(--text-dim);
            margin-bottom: 6px;
        }
        .reply-to-display {
            font-family: 'JetBrains Mono', monospace;
            font-size: 12px;
            color: var(--cyan);
            background: var(--cyan-dim);
            padding: 10px 14px;
            border-radius: var(--radius-sm);
            margin-bottom: 14px;
            word-break: break-all;
        }
        .reply-subject-inp, .reply-textarea {
            width: 100%;
            background: var(--bg-glass);
            border: 1px solid var(--border);
            border-radius: var(--radius-sm);
            padding: 10px 14px;
            font-family: 'JetBrains Mono', monospace;
            font-size: 12px;
            color: var(--text-primary);
            outline: none;
            margin-bottom: 12px;
        }
        .reply-subject-inp:focus, .reply-textarea:focus { border-color: var(--cyan); }
        .reply-textarea { resize: vertical; min-height: 100px; }
        .reply-footer {
            display: flex;
            justify-content: space-between;
            align-items: center;
            gap: 12px;
            flex-wrap: wrap;
        }
        .reply-note-txt {
            font-family: 'JetBrains Mono', monospace;
            font-size: 9px;
            color: var(--text-dim);
        }
        .btn-send {
            background: linear-gradient(135deg, var(--violet), var(--magenta));
            color: white;
            border: none;
            padding: 10px 24px;
            border-radius: var(--radius-sm);
            font-weight: 700;
            cursor: pointer;
            display: flex;
            align-items: center;
            gap: 8px;
            transition: all 0.2s;
        }
        .btn-send:hover { transform: translateY(-2px); filter: brightness(1.05); }

        .features {
            max-width: 1300px;
            margin: 0 auto;
            padding: 0 24px 80px;
        }
        .sec-lbl {
            font-family: 'JetBrains Mono', monospace;
            font-size: 11px;
            letter-spacing: 5px;
            text-transform: uppercase;
            color: var(--cyan);
            margin-bottom: 12px;
        }
        .sec-ttl {
            font-size: 32px;
            font-weight: 800;
            letter-spacing: -1px;
            margin-bottom: 32px;
        }
        .feat-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 16px;
            margin-bottom: 60px;
        }
        .feat-card {
            background: var(--bg-card);
            border: 1px solid var(--border);
            border-radius: var(--radius);
            padding: 28px 24px;
            transition: all 0.25s;
        }
        .feat-card:hover {
            border-color: var(--border-bright);
            transform: translateY(-4px);
        }
        .feat-ico { font-size: 32px; margin-bottom: 16px; display: block; }
        .feat-ttl { font-size: 17px; font-weight: 700; margin-bottom: 10px; }
        .feat-desc { font-size: 13px; color: var(--text-secondary); line-height: 1.6; }

        .faq {
            display: flex;
            flex-direction: column;
            gap: 12px;
            margin-bottom: 60px;
        }
        .faq-item {
            background: var(--bg-card);
            border: 1px solid var(--border);
            border-radius: var(--radius);
            overflow: hidden;
        }
        .faq-q {
            padding: 18px 24px;
            font-size: 15px;
            font-weight: 700;
            cursor: pointer;
            display: flex;
            justify-content: space-between;
            align-items: center;
            transition: color 0.2s;
        }
        .faq-q:hover { color: var(--cyan); }
        .faq-arr { font-size: 20px; transition: transform 0.25s; }
        .faq-item.open .faq-arr { transform: rotate(45deg); }
        .faq-a { max-height: 0; overflow: hidden; transition: max-height 0.3s ease; }
        .faq-item.open .faq-a { max-height: 200px; }
        .faq-a-in {
            padding: 0 24px 20px;
            font-size: 13px;
            color: var(--text-secondary);
            line-height: 1.7;
        }

        footer {
            border-top: 1px solid var(--border);
            padding: 28px 40px;
            display: flex;
            justify-content: space-between;
            flex-wrap: wrap;
            gap: 12px;
        }
        .foot-txt {
            font-family: 'JetBrains Mono', monospace;
            font-size: 11px;
            color: var(--text-dim);
        }
        .foot-txt a { color: var(--cyan); text-decoration: none; }

        .modal {
            display: none;
            position: fixed;
            top: 0; left: 0;
            width: 100%; height: 100%;
            background: rgba(0,0,0,0.8);
            z-index: 1000;
            justify-content: center;
            align-items: center;
        }
        .modal-content {
            background: var(--bg-card);
            border-radius: var(--radius-lg);
            padding: 28px;
            text-align: center;
            max-width: 380px;
            border: 1px solid var(--border);
        }
        .close-modal {
            background: linear-gradient(135deg, var(--cyan), var(--violet));
            color: white;
            border: none;
            padding: 10px 24px;
            border-radius: var(--radius-sm);
            cursor: pointer;
            margin-top: 18px;
        }

        .toasts {
            position: fixed;
            bottom: 24px;
            right: 24px;
            z-index: 9999;
            display: flex;
            flex-direction: column;
            gap: 8px;
        }
        .toast {
            background: var(--bg-card);
            border: 1px solid var(--border);
            padding: 12px 20px;
            border-radius: var(--radius-sm);
            font-size: 13px;
            font-weight: 500;
            animation: pop-in 0.3s forwards;
            box-shadow: 0 4px 20px rgba(0,0,0,0.2);
        }
        @keyframes pop-in { from{opacity:0;transform:translateY(12px)} to{opacity:1;transform:none} }
        
        .spin {
            width: 16px; height: 16px;
            border: 2px solid rgba(255,255,255,0.2);
            border-top-color: white;
            border-radius: 50%;
            animation: rotate 0.7s linear infinite;
            display: inline-block;
        }
        @keyframes rotate { to { transform: rotate(360deg); } }
        
        .checkbox-label {
            display: flex;
            align-items: center;
            gap: 8px;
            font-size: 11px;
            cursor: pointer;
        }
        .select-controls {
            display: flex;
            gap: 12px;
            align-items: center;
            flex-wrap: wrap;
        }
    </style>
</head>
<body>

<div class="bg-canvas">
    <div class="orb orb-1"></div>
    <div class="orb orb-2"></div>
    <div class="orb orb-3"></div>
</div>

<div class="wrap">

<nav>
    <a class="logo" href="#">
        <div class="logo-icon">✉</div>
        <span class="logo-text">Void<em>Mail</em></span>
    </a>
    <div class="nav-right">
        <div class="nav-pill" id="theme-toggle" onclick="toggleTheme()">
            <span>🌓</span> <span id="theme-text">Dark</span>
        </div>
        <div class="nav-pill"><span class="status-dot"></span>Logged in as <strong>{{ username }}</strong></div>
        <div class="nav-pill" onclick="logout()">🚪 Logout</div>
        <div class="nav-pill" id="email-status">📧 Ready</div>
    </div>
</nav>

<div class="ticker">
    <div class="ticker-track">
        <span class="t-item">Choose your own username</span>
        <span class="t-item">Working domains only</span>
        <span class="t-item">QR code sharing</span>
        <span class="t-item">Dark/Light mode</span>
        <span class="t-item">Bulk delete support</span>
        <span class="t-item">Fast OTP delivery</span>
        <span class="t-item">Spam detection</span>
        <span class="t-item">Anonymous replies</span>
        <span class="t-item">Multi-user support</span>
        <span class="t-item">Choose your own username</span>
    </div>
</div>

<section class="hero">
    <div class="hero-tag">Fresh Session · Fast OTP</div>
    <h1>Temp Email That<br><span class="g-text">Actually Works.</span></h1>
    <p class="hero-sub">Choose your own username. Get OTPs fast. Complete privacy with bulk delete.</p>

    <div class="ebar-wrap">
        <div class="custom-options">
            <input type="text" id="custom-username" class="username-input" placeholder="Choose username (samiya, raj, business)" maxlength="20">
            <select id="domain-select" class="domain-select">
                <option value="@guerrillamailblock.com">📧 @guerrillamailblock.com (Fastest)</option>
                <option value="@guerrillamail.com">📧 @guerrillamail.com</option>
                <option value="@guerrillamail.net">📧 @guerrillamail.net</option>
                <option value="@sharklasers.com">📧 @sharklasers.com</option>
            </select>
        </div>
        <div class="ebar" id="ebar">
            <div class="ebar-info">
                <div class="ebar-lbl">// email address</div>
                <div id="email-addr" class="empty">click generate to conjure your inbox…</div>
                <div class="expiry-row" id="expiry-row" style="opacity:0">
                    <div class="expiry-bar-bg"><div class="expiry-bar-fill" id="expiry-fill"></div></div>
                    <div class="expiry-time" id="expiry-txt">01:00:00</div>
                </div>
            </div>
            <div class="ebar-btns">
                <button class="ic-btn" id="btn-copy" onclick="copyEmail()" title="Copy" disabled>📋</button>
                <button class="ic-btn" id="btn-qr" onclick="showQR()" title="QR Code" disabled>📱</button>
                <button class="ic-btn" id="btn-refresh" onclick="refreshInbox()" title="Refresh" disabled>↻</button>
                <button class="btn-gen" id="btn-gen" onclick="generateInbox()">⚡ Generate New Inbox</button>
                <button class="btn-del" id="btn-del" onclick="deleteInbox()" disabled>🗑 Inbox</button>
            </div>
        </div>
    </div>
</section>

<div class="main-grid">
    <div class="panel">
        <div class="panel-hd">
            <span style="font-weight:700;">📬 Inbox</span>
            <span class="badge" id="msg-count">0 messages</span>
        </div>
        <div class="bulk-controls" id="bulk-controls" style="display: none;">
            <div class="select-controls">
                <label class="checkbox-label">
                    <input type="checkbox" id="select-all-checkbox" onchange="toggleSelectAll()">
                    <span>Select All</span>
                </label>
                <button class="bulk-btn" onclick="selectBySpamLevel()">⚠ Select Spam</button>
            </div>
            <button class="delete-selected-btn" id="delete-selected-btn" onclick="deleteSelected()" disabled>
                🗑 Delete Selected (<span id="selected-count">0</span>)
            </button>
        </div>
        <div class="mail-list" id="mail-list">
            <div class="empty-state">
                <div class="empty-ico">📭</div>
                <div class="empty-ttl">Click Generate to Start</div>
            </div>
        </div>
    </div>

    <div class="panel" id="viewer-panel">
        <div class="viewer-empty">
            <div class="viewer-empty-ico">📩</div>
            <div class="viewer-empty-txt">Select a message to read it</div>
        </div>
    </div>
</div>

<section class="features">
    <div class="sec-lbl">// Why VoidMail</div>
    <div class="sec-ttl">Complete Privacy. Zero Caching.</div>
    <div class="feat-grid">
        <div class="feat-card"><span class="feat-ico">🔄</span><div class="feat-ttl">Fresh Every Time</div><div class="feat-desc">No localStorage, no saved sessions. Every page load gives you a clean slate.</div></div>
        <div class="feat-card"><span class="feat-ico">📦</span><div class="feat-ttl">Bulk Delete</div><div class="feat-desc">Select multiple emails at once and delete them with one click.</div></div>
        <div class="feat-card"><span class="feat-ico">🎯</span><div class="feat-ttl">Smart Selection</div><div class="feat-desc">One-click select all spam emails or manually choose which ones to keep.</div></div>
        <div class="feat-card"><span class="feat-ico">🗑️</span><div class="feat-ttl">Individual Delete</div><div class="feat-desc">Hover over any email and click the delete icon to remove just that message.</div></div>
        <div class="feat-card"><span class="feat-ico">🛡️</span><div class="feat-ttl">Spam Detection</div><div class="feat-desc">Every email is analyzed for spam. Use "Select Spam" to quickly identify threats.</div></div>
        <div class="feat-card"><span class="feat-ico">🕵️</span><div class="feat-ttl">Anonymous Replies</div><div class="feat-desc">Reply without revealing your identity. Your temp address protects your privacy.</div></div>
        <div class="feat-card"><span class="feat-ico">📱</span><div class="feat-ttl">QR Code Share</div><div class="feat-desc">Share your temporary email via QR code. Scan and email instantly!</div></div>
        <div class="feat-card"><span class="feat-ico">✏️</span><div class="feat-ttl">Custom Username</div><div class="feat-desc">Choose your own username! No more random strings. Be samiya@temp.in</div></div>
    </div>

    <div class="sec-lbl">// FAQ</div>
    <div class="sec-ttl">Common questions.</div>
    <div class="faq">
        <div class="faq-item"><div class="faq-q" onclick="this.closest('.faq-item').classList.toggle('open')">Why don't I see old emails?<span class="faq-arr">+</span></div><div class="faq-a"><div class="faq-a-in">We don't save any sessions or cache emails. Every time you generate a new inbox, you start completely fresh with no old data.</div></div></div>
        <div class="faq-item"><div class="faq-q" onclick="this.closest('.faq-item').classList.toggle('open')">How do I delete multiple emails?<span class="faq-arr">+</span></div><div class="faq-a"><div class="faq-a-in">Check the boxes next to emails you want to delete, then click "Delete Selected". You can also click "Select All" or "Select Spam" for quick selection.</div></div></div>
        <div class="faq-item"><div class="faq-q" onclick="this.closest('.faq-item').classList.toggle('open')">Can I choose my own username?<span class="faq-arr">+</span></div><div class="faq-a"><div class="faq-a-in">Yes! Enter your desired username (3-20 characters, letters, numbers, underscore, hyphen) and select your favorite domain.</div></div></div>
        <div class="faq-item"><div class="faq-q" onclick="this.closest('.faq-item').classList.toggle('open')">How do I share my email via QR?<span class="faq-arr">+</span></div><div class="faq-a"><div class="faq-a-in">After generating your email, click the QR button (📱). Scan the code with any phone camera to email you instantly.</div></div></div>
        <div class="faq-item"><div class="faq-q" onclick="this.closest('.faq-item').classList.toggle('open')">How long do emails stay?<span class="faq-arr">+</span></div><div class="faq-a"><div class="faq-a-in">Emails stay as long as your inbox is active (up to 1 hour) or until you delete them manually.</div></div></div>
        <!-- ✅ FIX 3: Changed to English -->
        <div class="faq-item"><div class="faq-q" onclick="this.closest('.faq-item').classList.toggle('open')">OTP not arriving?<span class="faq-arr">+</span></div><div class="faq-a"><div class="faq-a-in">Wait 30-60 seconds, then Refresh. Some websites block disposable emails, try another domain.</div></div></div>
    </div>
</section>

<footer>
    <div class="foot-txt">© 2025 VoidMail · Fresh Sessions · No Cache · Multi-User</div>
    <div class="foot-txt">// Custom Username · QR Share · Bulk delete · Select spam · Fast OTP</div>
</footer>

</div>

<div id="qr-modal" class="modal">
    <div class="modal-content">
        <h3>📱 Share this email via QR</h3>
        <div id="qr-image" style="margin: 20px 0;"></div>
        <p id="qr-email" style="font-size: 12px; word-break: break-all;"></p>
        <button class="close-modal" onclick="closeQR()">Close</button>
    </div>
</div>

<div class="toasts" id="toasts"></div>

<script>
let token = null;
let currentEmail = null;
let messages = [];
let selectedMessages = new Set();
let currentMsgId = null;
let currentMsgFrom = null;
let currentMsgSubject = null;
let expiryEndTime = null;
let expiryTimer = null;
const EXPIRY_MS = 24 * 60 * 60 * 1000;

function toggleTheme() {
    const html = document.documentElement;
    const current = html.getAttribute('data-theme');
    const next = current === 'dark' ? 'light' : 'dark';
    html.setAttribute('data-theme', next);
    localStorage.setItem('theme', next);
    document.getElementById('theme-text').textContent = next === 'dark' ? 'Dark' : 'Light';
}

const savedTheme = localStorage.getItem('theme');
if (savedTheme) {
    document.documentElement.setAttribute('data-theme', savedTheme);
    document.getElementById('theme-text').textContent = savedTheme === 'dark' ? 'Dark' : 'Light';
}

function toast(msg, isError = false) {
    const el = document.createElement('div');
    el.className = 'toast';
    el.style.borderLeft = `3px solid ${isError ? 'var(--red)' : 'var(--green)'}`;
    el.innerHTML = `${isError ? '⚠️' : '✓'} ${msg}`;
    document.getElementById('toasts').appendChild(el);
    setTimeout(() => { el.style.opacity = '0'; setTimeout(() => el.remove(), 300); }, 3000);
}

function escapeHtml(str) {
    if (!str) return '';
    return String(str).replace(/[&<>]/g, function(m) {
        if (m === '&') return '&amp;';
        if (m === '<') return '&lt;';
        if (m === '>') return '&gt;';
        return m;
    });
}

async function generateInbox() {
    const username = document.getElementById('custom-username').value.trim();
    const domain = document.getElementById('domain-select').value;
    const btn = document.getElementById('btn-gen');
    btn.disabled = true;
    btn.innerHTML = '<div class="spin"></div> Conjuring…';
    
    try {
        const res = await fetch('/api/create_account', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ custom_username: username, selected_domain: domain })
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.error);
        
        token = data.token;
        currentEmail = data.address;
        expiryEndTime = Date.now() + EXPIRY_MS;
        
        document.getElementById('email-addr').textContent = currentEmail;
        document.getElementById('email-addr').classList.remove('empty');
        document.getElementById('ebar').classList.add('live');
        document.getElementById('btn-copy').disabled = false;
        document.getElementById('btn-qr').disabled = false;
        document.getElementById('btn-refresh').disabled = false;
        document.getElementById('btn-del').disabled = false;
        document.getElementById('expiry-row').style.opacity = '1';
        
        messages = [];
        selectedMessages.clear();
        renderList();
        startExpiryTimer();
        toast(`✨ Inbox created: ${currentEmail}`);
        refreshInbox();
        
        if (window.pollInterval) clearInterval(window.pollInterval);
        window.pollInterval = setInterval(() => { if(token) refreshInbox(); }, 5000);
        
    } catch (e) {
        toast(e.message, true);
    } finally {
        btn.disabled = false;
        btn.innerHTML = '⚡ Generate New Inbox';
    }
}

function startExpiryTimer() {
    if (expiryTimer) clearInterval(expiryTimer);
    updateExpiryDisplay();
    expiryTimer = setInterval(updateExpiryDisplay, 1000);
}

function updateExpiryDisplay() {
    if (!expiryEndTime) return;
    const remaining = Math.max(0, expiryEndTime - Date.now());
    const pct = (remaining / EXPIRY_MS) * 100;
    const hours = Math.floor(remaining / 3600000);
    const mins = Math.floor((remaining % 3600000) / 60000);
    const secs = Math.floor((remaining % 60000) / 1000);
    document.getElementById('expiry-fill').style.width = pct + '%';
    document.getElementById('expiry-txt').textContent = `${String(hours).padStart(2,'0')}:${String(mins).padStart(2,'0')}:${String(secs).padStart(2,'0')}`;
    if (remaining === 0) { clearInterval(expiryTimer); toast('📭 Inbox expired', true); }
}

async function refreshInbox() {
    if (!token) return;
    try {
        const res = await fetch('/api/get_messages');
        if (res.status === 401) { toast('Session expired', true); return; }
        const newMessages = await res.json();
        const existingIds = new Set(messages.map(m => m.id));
        for (const msg of newMessages) {
            if (!existingIds.has(msg.id)) messages.unshift(msg);
        }
        renderList();
    } catch (e) { console.error(e); }
}

function renderList() {
    const list = document.getElementById('mail-list');
    document.getElementById('msg-count').textContent = messages.length + ' message' + (messages.length !== 1 ? 's' : '');
    const bulkControls = document.getElementById('bulk-controls');
    bulkControls.style.display = messages.length ? 'flex' : 'none';
    
    if (!messages.length) {
        list.innerHTML = `<div class="viewer-empty"><div class="viewer-empty-ico">📭</div><div class="viewer-empty-txt">No messages yet<br>${currentEmail ? 'Share: ' + currentEmail : 'Generate inbox first'}<br>Wait 30-60 sec for OTP</div></div>`;
        return;
    }
    
    list.innerHTML = messages.map(m => {
        const spam = m._spam || { level: 'CLEAN' };
        const spamLabel = { CLEAN: '✓', LOW: '⚠', MEDIUM: '⚠⚠', HIGH: '✕' };
        const isChecked = selectedMessages.has(m.id);
        return `<div class="mail-item" onclick="openMessage('${m.id}', this)">
            <div class="mail-checkbox" onclick="event.stopPropagation()">
                <input type="checkbox" ${isChecked ? 'checked' : ''} onchange="toggleSelect('${m.id}', this.checked)">
            </div>
            <div class="mail-content">
                <div class="mail-from">${escapeHtml(m.from?.address || 'unknown')}</div>
                <div class="mail-subject">${escapeHtml(m.subject || '(no subject)')}</div>
                <div class="mail-time">${new Date(m.createdAt).toLocaleString()}</div>
            </div>
            <span class="spam-badge spam-${spam.level}">${spamLabel[spam.level]}</span>
        </div>`;
    }).join('');
    updateSelectedCount();
}

function toggleSelect(id, checked) {
    if (checked) selectedMessages.add(id);
    else selectedMessages.delete(id);
    updateSelectedCount();
    const selectAll = document.getElementById('select-all-checkbox');
    if (selectAll) selectAll.checked = selectedMessages.size === messages.length && messages.length > 0;
}

function toggleSelectAll() {
    const cb = document.getElementById('select-all-checkbox');
    if (cb.checked) messages.forEach(m => selectedMessages.add(m.id));
    else selectedMessages.clear();
    renderList();
}

function selectBySpamLevel() {
    selectedMessages.clear();
    messages.forEach(m => {
        const spam = m._spam || { level: 'CLEAN' };
        if (spam.level === 'HIGH' || spam.level === 'MEDIUM') selectedMessages.add(m.id);
    });
    renderList();
    toast(`Selected ${selectedMessages.size} spam emails`);
}

function updateSelectedCount() {
    document.getElementById('selected-count').textContent = selectedMessages.size;
    const btn = document.getElementById('delete-selected-btn');
    if (btn) btn.disabled = selectedMessages.size === 0;
}

function deleteSelected() {
    if (selectedMessages.size === 0) return;
    if (confirm(`Delete ${selectedMessages.size} message(s)?`)) {
        messages = messages.filter(m => !selectedMessages.has(m.id));
        selectedMessages.clear();
        renderList();
        if (currentMsgId && !messages.find(m => m.id === currentMsgId)) {
            document.getElementById('viewer-panel').innerHTML = `<div class="viewer-empty"><div class="viewer-empty-ico">📩</div><div class="viewer-empty-txt">Message deleted</div></div>`;
            currentMsgId = null;
        }
        toast('Messages deleted');
    }
}

async function openMessage(id, el) {
    document.querySelectorAll('.mail-item').forEach(i => i.classList.remove('active'));
    if (el) el.classList.add('active');
    currentMsgId = id;
    const panel = document.getElementById('viewer-panel');
    panel.innerHTML = `<div class="viewer-empty"><div class="spin"></div> Loading...</div>`;
    
    try {
        const res = await fetch('/api/get_message/' + id);
        const msg = await res.json();
        currentMsgFrom = msg.from?.address || '';
        currentMsgSubject = msg.subject || '';
        const spam = msg._spam || { level: 'CLEAN', score: 0, flags: [] };
        
        panel.innerHTML = `
            <div class="viewer-hd">
                <div class="viewer-subject">${escapeHtml(msg.subject || '(no subject)')}</div>
                <div class="viewer-meta">
                    <div>📧 From: ${escapeHtml(currentMsgFrom)}</div>
                    <div>📅 ${new Date(msg.createdAt).toLocaleString()}</div>
                </div>
                ${spam.level !== 'CLEAN' ? `<div style="margin-top: 8px; color: var(--red); font-size: 11px;">⚠ Spam Score: ${spam.score}/100<br>${spam.flags.join(', ')}</div>` : ''}
            </div>
            <div style="padding: 20px 24px; background: var(--bg-glass); margin: 0 20px 20px; border-radius: var(--radius-sm);">
                <div style="white-space: pre-wrap; word-break: break-word; font-family: monospace; font-size: 13px;">${escapeHtml(msg.text || '(No content)')}</div>
            </div>
            <div class="reply-section" id="reply-section">
                <div class="reply-toggle" onclick="toggleReply()">
                    <div class="reply-toggle-ttl">✉ Anonymous Secure Reply</div>
                    <span class="reply-toggle-arr">▼</span>
                </div>
                <div class="reply-body">
                    <div class="reply-inner">
                        <div class="reply-anon-note">🕵️ Anonymous mode. Reply will be sent from <strong>${escapeHtml(currentEmail)}</strong></div>
                        <div class="reply-field-lbl">// replying to</div>
                        <div class="reply-to-display">${escapeHtml(currentMsgFrom)}</div>
                        <div class="reply-field-lbl">// subject</div>
                        <input class="reply-subject-inp" id="reply-subject" value="Re: ${escapeHtml(msg.subject || '(no subject)')}">
                        <div class="reply-field-lbl">// message</div>
                        <textarea class="reply-textarea" id="reply-body" placeholder="Type your anonymous reply here..."></textarea>
                        <div class="reply-footer">
                            <div class="reply-note-txt">Your real identity stays hidden</div>
                            <button class="btn-send" onclick="sendReply()">🕵️ Send Anonymously</button>
                        </div>
                    </div>
                </div>
            </div>`;
    } catch (e) {
        panel.innerHTML = `<div class="viewer-empty"><div class="viewer-empty-ico">⚠️</div><div class="viewer-empty-txt">Failed to load</div></div>`;
    }
}

function toggleReply() {
    const sec = document.getElementById('reply-section');
    if (sec) sec.classList.toggle('open');
}

async function sendReply() {
    if (!token || !currentMsgFrom) { toast('No active session', true); return; }
    const body = document.getElementById('reply-body')?.value.trim();
    const subject = document.getElementById('reply-subject')?.value.trim();
    if (!body) { toast('Please write a message', true); return; }
    
    const btn = document.querySelector('.btn-send');
    const originalText = btn.innerHTML;
    btn.disabled = true;
    btn.innerHTML = '<div class="spin"></div>';
    
    try {
        const res = await fetch('/api/send_reply', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ to: currentMsgFrom, subject: subject, text: body })
        });
        const data = await res.json();
        if (data.success) {
            toast('✅ Reply sent! ' + (data.message || ''), false);
            document.getElementById('reply-body').value = '';
        } else {
            toast('⚠️ ' + (data.message || 'Failed to send'), true);
        }
    } catch (e) { toast('❌ Network error', true); }
    finally { btn.disabled = false; btn.innerHTML = originalText; }
}

function copyEmail() {
    if (!currentEmail) { toast('Generate email first', true); return; }
    navigator.clipboard.writeText(currentEmail);
    toast('📋 Email copied!');
}

async function showQR() {
    if (!currentEmail) { toast('Generate email first', true); return; }
    const qrUrl = `https://api.qrserver.com/v1/create-qr-code/?size=200x200&data=mailto:${currentEmail}`;
    document.getElementById('qr-image').innerHTML = `<img src="${qrUrl}" style="max-width: 200px; border-radius: 10px;">`;
    document.getElementById('qr-email').textContent = currentEmail;
    document.getElementById('qr-modal').style.display = 'flex';
}

function closeQR() { document.getElementById('qr-modal').style.display = 'none'; }
function deleteInbox() { if(confirm('Delete all messages?')) location.reload(); }
function logout() { window.location.href = '/logout'; }

async function loadUserState() {
    try {
        const res = await fetch('/api/user_state');
        const data = await res.json();
        if (data.has_email) {
            token = data.token;
            currentEmail = data.email;
            expiryEndTime = data.expiry * 1000;
            document.getElementById('email-addr').textContent = currentEmail;
            document.getElementById('email-addr').classList.remove('empty');
            document.getElementById('ebar').classList.add('live');
            document.getElementById('btn-copy').disabled = false;
            document.getElementById('btn-qr').disabled = false;
            document.getElementById('btn-refresh').disabled = false;
            document.getElementById('btn-del').disabled = false;
            document.getElementById('expiry-row').style.opacity = '1';
            startExpiryTimer();
            refreshInbox();
            if (window.pollInterval) clearInterval(window.pollInterval);
            window.pollInterval = setInterval(() => { if(token) refreshInbox(); }, 5000);
        }
    } catch(e) { console.log('No existing session'); }
}

loadUserState();
</script>
</body>
</html>
"""

if __name__ == '__main__':
    print("\n" + "="*60)
    print("🚀 VoidMail Server Running with Multi-User Support!")
    print("="*60)
    print("✅ Fix 1: Auto-login after registration")
    print("✅ Fix 2: Case-insensitive login (User not found fixed)")
    print("✅ Fix 3: FAQ changed to English")
    print("✅ All original features intact")
    print("📍 http://localhost:5000")
    print("="*60 + "\n")
    app.run(debug=True, host='0.0.0.0', port=5000)
import sqlite3
from flask import Flask, render_template, request, jsonify, session
from flask_cors import CORS

app = Flask(__name__)
CORS(app)
app.secret_key = 'payplus_secure_key_wajih_2026'

# --- 1. إعداد قاعدة البيانات ---
def get_db():
    conn = sqlite3.connect('payplus.db', check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db() as conn:
        # جدول المستخدمين
        conn.execute('''CREATE TABLE IF NOT EXISTS users 
            (id INTEGER PRIMARY KEY AUTOINCREMENT, 
             tg_id TEXT UNIQUE, 
             name TEXT, 
             balance REAL DEFAULT 0)''')
        
        # جدول السحوبات
        conn.execute('''CREATE TABLE IF NOT EXISTS withdrawals 
            (id INTEGER PRIMARY KEY AUTOINCREMENT, 
             user_id INTEGER, 
             method TEXT, 
             amount REAL, 
             status TEXT, 
             details TEXT, 
             date TIMESTAMP DEFAULT (DATETIME('now', 'localtime')))''')
        conn.commit()

# --- 2. مسارات الصفحات ---

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/admin')
def admin():
    with get_db() as conn:
        # جلب طلبات السحب المعلقة
        withdrawals = conn.execute('''
            SELECT withdrawals.*, users.name 
            FROM withdrawals 
            JOIN users ON withdrawals.user_id = users.id 
            WHERE withdrawals.status = 'قيد المراجعة'
            ORDER BY date DESC
        ''').fetchall()
        
        # جلب العدد الحقيقي للمستخدمين
        user_count = conn.execute('SELECT COUNT(*) FROM users').fetchone()[0]
        
    return render_template('admin.html', withdrawals=withdrawals, user_count=user_count)

# --- 3. الأوامر البرمجية (API) ---

# تسجيل الدخول التلقائي بتلجرام
@app.route('/api/auth', methods=['POST'])
def auth():
    data = request.json
    tg_id = str(data.get('user_id'))
    name = data.get('name')
    
    with get_db() as conn:
        user = conn.execute("SELECT * FROM users WHERE tg_id = ?", (tg_id,)).fetchone()
        if not user:
            conn.execute("INSERT INTO users (tg_id, name) VALUES (?, ?)", (tg_id, name))
            conn.commit()
            user = conn.execute("SELECT * FROM users WHERE tg_id = ?", (tg_id,)).fetchone()
        
        session['user_id'] = user['id']
        return jsonify({"success": True, "balance": user['balance']})

# إكمال مهمة وزيادة رصيد
@app.route('/api/complete-task', methods=['POST'])
def complete_task():
    if 'user_id' not in session:
        return jsonify({"success": False, "message": "غير مسجل"})
    
    data = request.json
    reward = float(data.get('reward'))
    uid = session['user_id']
    
    with get_db() as conn:
        conn.execute("UPDATE users SET balance = balance + ? WHERE id = ?", (reward, uid))
        conn.commit()
        updated = conn.execute("SELECT balance FROM users WHERE id = ?", (uid,)).fetchone()
        return jsonify({"success": True, "new_balance": updated['balance']})

# طلب سحب جديد
@app.route('/api/withdraw', methods=['POST'])
def withdraw():
    if 'user_id' not in session:
        return jsonify({"success": False, "message": "يجب تسجيل الدخول"})
    
    data = request.json
    uid = session['user_id']
    amount = float(data.get('amount'))
    method = data.get('method')
    details = data.get('details')

    with get_db() as conn:
        user = conn.execute("SELECT balance FROM users WHERE id = ?", (uid,)).fetchone()
        if user['balance'] < amount:
            return jsonify({"success": False, "message": "رصيدك غير كافٍ"})
        
        # خصم الرصيد وتسجيل الطلب
        conn.execute("UPDATE users SET balance = balance - ? WHERE id = ?", (amount, uid))
        conn.execute('''INSERT INTO withdrawals (user_id, method, amount, status, details) 
                        VALUES (?, ?, ?, ?, ?)''', (uid, method, amount, "قيد المراجعة", details))
        conn.commit()
        
        updated = conn.execute("SELECT balance FROM users WHERE id = ?", (uid,)).fetchone()
        return jsonify({"success": True, "new_balance": updated['balance']})

# موافقة الأدمن على السحب
@app.route('/api/admin/approve/<int:w_id>', methods=['POST'])
def approve(w_id):
    with get_db() as conn:
        conn.execute("UPDATE withdrawals SET status = 'تم الدفع ✅' WHERE id = ?", (w_id,))
        conn.commit()
    return jsonify({"success": True})

if __name__ == '__main__':
    init_db()
    app.run(host='0.0.0.0', port=5000)

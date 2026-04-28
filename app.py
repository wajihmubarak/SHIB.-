import sqlite3
from flask import Flask, render_template, request, jsonify, session
from flask_cors import CORS

app = Flask(__name__)
CORS(app)
app.secret_key = 'wajih_pro_secure_2026'

# --- 1. إعداد قاعدة البيانات ---
def get_db():
    # الاتصال بقاعدة البيانات وتفعيل نظام الصفوف كقاموس لسهولة الوصول
    conn = sqlite3.connect('payplus.db', check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db() as conn:
        # جدول المستخدمين: لحفظ بيانات المشتركين ورصيدهم
        conn.execute('''CREATE TABLE IF NOT EXISTS users 
            (id INTEGER PRIMARY KEY AUTOINCREMENT, 
             tg_id TEXT UNIQUE, 
             name TEXT, 
             balance REAL DEFAULT 0)''')
        
        # جدول السحوبات: تم استخدام CURRENT_TIMESTAMP لحل مشكلة Render
        conn.execute('''CREATE TABLE IF NOT EXISTS withdrawals 
            (id INTEGER PRIMARY KEY AUTOINCREMENT, 
             user_id INTEGER, 
             method TEXT, 
             amount REAL, 
             status TEXT, 
             details TEXT, 
             date TEXT DEFAULT CURRENT_TIMESTAMP)''')
        
        # جدول المهام المكتملة: لمنع تكرار الربح من نفس المهمة
        conn.execute('''CREATE TABLE IF NOT EXISTS completed_tasks 
            (user_id INTEGER, 
             task_id TEXT, 
             UNIQUE(user_id, task_id))''')
        conn.commit()

# --- 2. مسارات الصفحات ---

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/admin')
def admin():
    with get_db() as conn:
        # جلب طلبات السحب المعلقة فقط
        withdrawals = conn.execute('''
            SELECT withdrawals.*, users.name 
            FROM withdrawals 
            JOIN users ON withdrawals.user_id = users.id 
            WHERE withdrawals.status = 'قيد المراجعة'
            ORDER BY date DESC
        ''').fetchall()
        
        # حساب العدد الحقيقي للمستخدمين في النظام
        user_count = conn.execute('SELECT COUNT(*) FROM users').fetchone()[0]
        
    return render_template('admin.html', withdrawals=withdrawals, user_count=user_count)

# --- 3. واجهة البرمجة (API) ---

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

@app.route('/api/complete-task', methods=['POST'])
def complete_task():
    if 'user_id' not in session:
        return jsonify({"success": False, "message": "سجل دخول أولاً"})
    
    uid = session['user_id']
    task_id = request.json.get('task_id')
    reward = float(request.json.get('reward'))

    with get_db() as conn:
        # فحص ما إذا كانت المهمة قد اكتملت سابقاً
        check = conn.execute("SELECT * FROM completed_tasks WHERE user_id = ? AND task_id = ?", (uid, task_id)).fetchone()
        if check:
            return jsonify({"success": False, "message": "هذه المهمة مكتملة بالفعل"})

        # تسجيل المهمة وتحديث الرصيد
        try:
            conn.execute("INSERT INTO completed_tasks (user_id, task_id) VALUES (?, ?)", (uid, task_id))
            conn.execute("UPDATE users SET balance = balance + ? WHERE id = ?", (reward, uid))
            conn.commit()
            
            new_balance = conn.execute("SELECT balance FROM users WHERE id = ?", (uid,)).fetchone()[0]
            return jsonify({"success": True, "new_balance": new_balance})
        except:
            return jsonify({"success": False, "message": "حدث خطأ أثناء المعالجة"})

@app.route('/api/user-tasks')
def get_user_tasks():
    if 'user_id' not in session:
        return jsonify([])
    with get_db() as conn:
        tasks = conn.execute("SELECT task_id FROM completed_tasks WHERE user_id = ?", (session['user_id'],)).fetchall()
    return jsonify([t['task_id'] for t in tasks])

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
        
        conn.execute("UPDATE users SET balance = balance - ? WHERE id = ?", (amount, uid))
        conn.execute('''INSERT INTO withdrawals (user_id, method, amount, status, details) 
                        VALUES (?, ?, ?, ?, ?)''', (uid, method, amount, "قيد المراجعة", details))
        conn.commit()
        
        updated = conn.execute("SELECT balance FROM users WHERE id = ?", (uid,)).fetchone()
        return jsonify({"success": True, "new_balance": updated['balance']})

@app.route('/api/admin/approve/<int:w_id>', methods=['POST'])
def approve(w_id):
    with get_db() as conn:
        conn.execute("UPDATE withdrawals SET status = 'تم الدفع ✅' WHERE id = ?", (w_id,))
        conn.commit()
    return jsonify({"success": True})
@app.route('/api/user-withdrawals')
def get_user_withdrawals():
    if 'user_id' not in session: return jsonify([])
    uid = session['user_id']
    with get_db() as conn:
        logs = conn.execute("SELECT amount, method, status, date FROM withdrawals WHERE user_id = ? ORDER BY date DESC", (uid,)).fetchall()
    
    # تحويل البيانات لتنسيق JSON
    return jsonify([dict(row) for row in logs])

if __name__ == '__main__':
    init_db()
    # تشغيل السيرفر على جميع المنافذ المتاحة
    app.run(host='0.0.0.0', port=5000)

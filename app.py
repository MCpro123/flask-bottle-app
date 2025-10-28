from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
import psycopg2
import psycopg2.extras
from datetime import datetime
import config  # contains POSTGRES_HOST, POSTGRES_DB, POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_PORT, SECRET_KEY
from datetime import datetime, timedelta

app = Flask(__name__)
app.secret_key = config.SECRET_KEY

# # PostgreSQL connection
# def get_db_connection():
#     conn = psycopg2.connect(
#         host=config.POSTGRES_HOST,
#         database=config.POSTGRES_DB,
#         user=config.POSTGRES_USER,
#         password=config.POSTGRES_PASSWORD,
#         port=config.POSTGRES_PORT
#     )
#     return conn
import os

def get_db_connection():
    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    return conn

# Initialize tables (run once at startup)
def init_db():
    conn = get_db_connection()
    cur = conn.cursor()
    
    cur.execute('''
        CREATE TABLE IF NOT EXISTS employees (
            id SERIAL PRIMARY KEY,
            name VARCHAR(100) NOT NULL,
            password VARCHAR(100) NOT NULL,
            is_admin BOOLEAN DEFAULT FALSE,
            is_active BOOLEAN DEFAULT TRUE
        )
    ''')

    cur.execute('''
        CREATE TABLE IF NOT EXISTS customers (
            id SERIAL PRIMARY KEY,
            name VARCHAR(100) NOT NULL,
            bottles INTEGER DEFAULT 0,
            latitude DOUBLE PRECISION,
            longitude DOUBLE PRECISION
        )
    ''')

    cur.execute('''
        CREATE TABLE IF NOT EXISTS bottle_records (
            id SERIAL PRIMARY KEY,
            employee_id INTEGER REFERENCES employees(id) ON DELETE CASCADE,
            customer_id INTEGER REFERENCES customers(id) ON DELETE SET NULL,
            latitude DOUBLE PRECISION,
            longitude DOUBLE PRECISION,
            bottles INTEGER,
            returned_bottles INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT NOW()
        )
    ''')
    
    # create default admin
    cur.execute("SELECT * FROM employees WHERE name='Admin'")
    if not cur.fetchone():
        cur.execute("INSERT INTO employees (name, password, is_admin) VALUES (%s, %s, %s)",
                    ("Admin", "admin123", True))
    
    conn.commit()
    cur.close()
    conn.close()

# ---------------- Routes ----------------

# Home page → login
@app.route('/', methods=['GET', 'POST'])
def login():
    msg = ''
    if request.method == 'POST' and 'employee_id' in request.form and 'password' in request.form:
        employee_id = request.form['employee_id']
        password = request.form['password']

        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cur.execute('SELECT * FROM employees WHERE id=%s AND password=%s AND is_active=TRUE', (employee_id, password))
        account = cur.fetchone()
        cur.close()
        conn.close()

        if account:
            session['loggedin'] = True
            session['employee_id'] = account['id']
            session['is_admin'] = account['is_admin']
            if account['is_admin']:
                return redirect(url_for('admin_dashboard'))
            return redirect(url_for('employee_page'))
        else:
            msg = 'Incorrect ID or Password!'
    return render_template('login.html', msg=msg)

# Employee dashboard
@app.route('/employee')
def employee_page():
    if session.get('loggedin') and not session.get('is_admin'):
        return render_template('employee.html', employee_id=session['employee_id'])
    return redirect(url_for('login'))

# Admin dashboard with map + employee management
@app.route('/admin')
def admin_dashboard():
    if session.get('loggedin') and session.get('is_admin'):
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

        # Fetch bottle records
        cur.execute('SELECT * FROM bottle_records')
        data = cur.fetchall()

        # Fetch employee list
        cur.execute('SELECT * FROM employees ORDER BY id ASC')
        employees = cur.fetchall()

        cur.close()
        conn.close()
        return render_template('admin.html', data=data, employees=employees)
    return redirect(url_for('login'))


@app.route('/get_customers')
def get_customers():
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cur.execute('SELECT id, name, phone, bottles, latitude, longitude FROM customers ORDER BY name ASC')
    customers = cur.fetchall()
    cur.close()
    conn.close()
    return jsonify([dict(row) for row in customers])


@app.route('/get_customer_bottles/<int:customer_id>')
def get_customer_bottles(customer_id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('SELECT name, phone, bottles FROM customers WHERE id=%s', (customer_id,))
    row = cur.fetchone()
    cur.close()
    conn.close()
    if not row:
        return jsonify({'status': 'not_found'})
    return jsonify({'status': 'found', 'name': row[0], 'phone': row[1], 'bottles': row[2]})


@app.route('/update_location', methods=['POST'])
def update_location():
    if 'loggedin' not in session:
        return jsonify({"status": "unauthorized"}), 403

    data = request.get_json()
    emp_id = session['employee_id']
    lat = data.get('lat')
    lon = data.get('lon')
    cust_type = data.get('type')
    count = int(data.get('count', 0))

    conn = get_db_connection()
    cur = conn.cursor()

    if cust_type == "new":
        name = data.get('name')
        phone = data.get('phone')
        if not name or not phone:
            return jsonify({'status': 'error', 'message': 'Name and phone required'})
        # Save new customer with location
        cur.execute('''
            INSERT INTO customers (name, phone, bottles, latitude, longitude)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id
        ''', (name, phone, count, lat, lon))
        customer_id = cur.fetchone()[0]
        cur.execute('''
        INSERT INTO bottle_records (employee_id, customer_id, latitude, longitude, bottles, created_at)
        VALUES (%s, %s, %s, %s, %s, NOW())
    ''', (emp_id, customer_id, lat, lon, count))
    else:
        customer_id = data.get('customer_id')
        returned = int(data.get('returned_bottles', 0))
        borrowed = int(data.get('borrowed_bottles', 0))
        cur.execute('SELECT latitude, longitude,bottles FROM customers WHERE id = %s', (customer_id,))
        row = cur.fetchone()
        lat, lon,prev_bottles = row
        prev_bottles = int(prev_bottles)
        new_bottles = prev_bottles - returned + borrowed

        # Only update bottle count, not location
        cur.execute('UPDATE customers SET bottles=%s WHERE id=%s', (new_bottles, customer_id))

        cur.execute('''
        INSERT INTO bottle_records (employee_id, customer_id, latitude, longitude, bottles,returned_bottles,borrowed_bottles,created_at)
        VALUES (%s, %s, %s, %s, %s,%s,%s NOW())
    ''', (emp_id, customer_id, lat, lon, new_bottles,returned,borrowed))
    

    conn.commit()
    cur.close()
    conn.close()
    return jsonify({"status": "success"})

# Get employee’s saved records
@app.route('/get_employee_records')
def get_employee_records():
    if not session.get("loggedin"):
        return jsonify([])

    employee_id = session["employee_id"]

    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cur.execute("""
        SELECT latitude, longitude, bottles 
        FROM bottle_records 
        WHERE employee_id = %s
    """, (employee_id,))
    rows = cur.fetchall()
    cur.close()
    conn.close()

    return jsonify(rows)

# Add new employee (Admin only)
@app.route('/add_employee', methods=['POST'])
def add_employee():
    if not session.get('loggedin') or not session.get('is_admin'):
        return jsonify({'status': 'unauthorized'}), 403

    name = request.form.get('name')
    password = request.form.get('password')

    if not name or not password:
        return jsonify({'status': 'error', 'message': 'Name and password required'}), 400

    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            "INSERT INTO employees (name, password, is_admin) VALUES (%s, %s, %s) RETURNING id",
            (name, password, False)
        )
        new_id = cur.fetchone()[0]
        conn.commit()
    except Exception as e:
        conn.rollback()
        cur.close()
        conn.close()
        return jsonify({'status': 'error', 'message': str(e)}), 500

    cur.close()
    conn.close()
    return jsonify({'status': 'success', 'employee_id': new_id})

# Search employee by ID
@app.route('/get_employee/<int:id>')
def get_employee(id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('SELECT id, name FROM employees WHERE id = %s', (id,))
    emp = cur.fetchone()
    cur.close()
    conn.close()

    if not emp:
        return jsonify({'status': 'not_found'})
    return jsonify({'status': 'found', 'id': emp[0], 'name': emp[1]})


# Delete employee by ID (AJAX)
@app.route('/delete_employee/<int:id>', methods=['DELETE'])
def delete_employee(id):
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute('SELECT id FROM employees WHERE id = %s', (id,))
    emp = cur.fetchone()
    if not emp:
        cur.close()
        conn.close()
        return jsonify({'status': 'error', 'message': 'Employee not found'})

    cur.execute('UPDATE employees SET is_active = FALSE WHERE id = %s', (id,))
    conn.commit()
    cur.close()
    conn.close()
    return jsonify({'status': 'success', 'message': 'Employee deleted'})

@app.route('/get_all_markers')
def get_all_markers():
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cur.execute("""
        SELECT 
            b.id AS record_id,
            c.latitude,
            c.longitude,
            c.bottles,
            e.id AS employee_id,
            e.name AS employee_name,
            c.id AS customer_id,
            c.name AS customer_name,
            c.phone AS customer_phone
        FROM bottle_records b
        JOIN employees e ON b.employee_id = e.id
        JOIN customers c ON b.customer_id = c.id
        WHERE b.latitude IS NOT NULL AND b.longitude IS NOT NULL
        ORDER BY b.created_at DESC
    """)
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return jsonify([dict(r) for r in rows])


@app.route('/get_employee_markers')
def get_employee_markers():
    
    emp_lat = request.args.get("lat", type=float)
    emp_lon = request.args.get("lon", type=float)
    radius_km = request.args.get("radius", default=5.0, type=float)  # adjustable radius


    if emp_lat is None or emp_lon is None:
        return jsonify({"status": "error", "message": "Missing latitude or longitude"}), 400

    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

        # Subquery computes distance_km; outer query filters by radius_km
        sql = """
        SELECT *
        FROM (
            SELECT 
                id AS customer_id,
                name AS customer_name,
                phone AS customer_phone,
                bottles AS customer_bottles,
                latitude,
                longitude,
                (
                    6371 * acos(
                        cos(radians(%s)) * cos(radians(latitude)) *
                        cos(radians(longitude) - radians(%s)) +
                        sin(radians(%s)) * sin(radians(latitude))
                    )
                ) AS distance_km
            FROM customers
            WHERE latitude IS NOT NULL AND longitude IS NOT NULL
        ) AS sub
        WHERE sub.distance_km <= %s
        ORDER BY sub.distance_km ASC;
        """

        cur.execute(sql, (emp_lat, emp_lon, emp_lat, radius_km))
        rows = cur.fetchall()
        cur.close()
        conn.close()


        data = [dict(row) for row in rows]
        return jsonify({"status": "success", "data": data})
    except Exception as e:
        print("DB error:", e)
        return jsonify({"status": "error", "message": str(e)}), 500
    


@app.route('/export_bottle_records')
def export_bottle_records():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT 
            b.id AS record_id,
            b.created_at,
            e.name AS employee_name,
            c.name AS customer_name,
            c.phone AS customer_phone,
            b.bottles,
            b.latitude,
            b.longitude
        FROM bottle_records b
        JOIN customers c ON b.customer_id = c.id
        JOIN employees e ON b.employee_id = e.id
        ORDER BY b.created_at DESC;
    """)
    rows = cur.fetchall()
    columns = [desc[0] for desc in cur.description]
    cur.close()
    conn.close()
    
    data = [dict(zip(columns, row)) for row in rows]
    return jsonify(data)

@app.route('/insights')
def insights_page():
    if not session.get('loggedin') or not session.get('is_admin'):
        return redirect(url_for('login'))
    return render_template('insights.html')


@app.route('/get_hourly_bottles')
def get_hourly_bottles():
    if not session.get('loggedin') or not session.get('is_admin'):
        return jsonify([])

    date_str = request.args.get('date')
    if date_str:
        try:
            date_obj = datetime.strptime(date_str, '%Y-%m-%d')
        except:
            return jsonify({'error': 'Invalid date format'}), 400
    else:
        date_obj = datetime.now()

    start_of_day = date_obj.replace(hour=0, minute=0, second=0, microsecond=0)
    end_of_day = start_of_day + timedelta(days=1)

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT EXTRACT(HOUR FROM created_at) AS hour, SUM(bottles) AS total_bottles
        FROM bottle_records
        WHERE created_at >= %s AND created_at < %s
        GROUP BY hour
        ORDER BY hour
    """, (start_of_day, end_of_day))

    rows = cur.fetchall()
    cur.close()
    conn.close()

    result = [{'hour': int(r[0]), 'total_bottles': int(r[1])} for r in rows]
    return jsonify(result)

@app.route('/get_daily_totals')
def get_daily_totals():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT DATE(created_at), SUM(borrowed_bottles)
        FROM bottle_records
        GROUP BY DATE(created_at)
        ORDER BY DATE(created_at)
    """)
    rows = cur.fetchall()
    cur.close(); conn.close()
    return jsonify([{'date': str(r[0]), 'total': int(r[1])} for r in rows])

@app.route('/get_avg_bottles')
def get_avg_bottles():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT AVG(bottles) FROM customers")
    avg = cur.fetchone()[0] or 0
    cur.close(); conn.close()
    return jsonify({'avg': avg})


@app.route('/get_returns_ratio')
def get_returns_ratio():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT SUM(returned_bottles), SUM(borrowed_bottles) FROM bottle_records")
    ret, delv = cur.fetchone()
    cur.close(); conn.close()
    return jsonify({'returned': int(ret or 0), 'delivered': int(delv or 0)})



# Logout
@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# ---------------- Main ----------------
if __name__ == '__main__':
    init_db()  # initialize Postgres tables
    app.run(debug=True)
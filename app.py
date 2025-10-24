from flask import Flask, render_template, request, redirect, url_for, session, jsonify
from flask_mysqldb import MySQL
import MySQLdb.cursors
import re

app = Flask(__name__)
app.config.from_pyfile('config.py')

mysql = MySQL(app)

# Home page → login
@app.route('/', methods=['GET', 'POST'])
def login():
    msg = ''
    if request.method == 'POST' and 'employee_id' in request.form and 'password' in request.form:
        employee_id = request.form['employee_id']
        password = request.form['password']
        cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
        cursor.execute('SELECT * FROM employees WHERE employee_id = %s AND password = %s', (employee_id, password))
        account = cursor.fetchone()
        if account:
            session['loggedin'] = True
            session['employee_id'] = account['employee_id']
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
    if 'loggedin' in session and not session['is_admin']:
        return render_template('employee.html', employee_id=session['employee_id'])
    return redirect(url_for('login'))

# Admin dashboard with map
@app.route('/admin')
def admin_dashboard():
    if session.get('loggedin') and session.get('is_admin'):
        cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
        cursor.execute('SELECT * FROM bottles')
        data = cursor.fetchall()
        cursor.close()
        return render_template('admin.html', data=data)
    return redirect(url_for('login'))

# Save employee’s current location
@app.route('/update_location', methods=['POST'])
def update_location():
    if 'loggedin' in session:
        data = request.get_json()
        lat = data.get('lat')
        lon = data.get('lon')
        count = data.get('count', 0)
        emp_id = session['employee_id']

        cursor = mysql.connection.cursor()
        cursor.execute(
            "REPLACE INTO bottles (employee_id, latitude, longitude, bottle_count) VALUES (%s, %s, %s, %s)",
            (emp_id, lat, lon, count)
        )
        mysql.connection.commit()
        return jsonify({'status': 'success'})
    return jsonify({'status': 'unauthorized'}), 403

@app.route('/get_employee_records')
def get_employee_records():
    if "user_id" not in session:
        return jsonify([])

    employee_id = session["user_id"]

    cur = mysql.connection.cursor()
    cur.execute("""
        SELECT latitude, longitude, bottles 
        FROM bottle_records 
        WHERE employee_id = %s
    """, (employee_id,))
    rows = cur.fetchall()
    cur.close()

    return jsonify(rows)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

if __name__ == '__main__':
    app.run(debug=True)




from flask import Flask, render_template, request, redirect, url_for, flash, session
from db import init_db, get_db
import random
import string
import os
from datetime import datetime
import hashlib

app = Flask(__name__)
app.secret_key = os.urandom(24)

# Inicializar la base de datos al iniciar la aplicación
@app.before_first_request
def initialize_database():
    init_db()

def generate_otp():
    return ''.join(random.choices(string.digits, k=6))

def hash_card_id(card_id):
    return hashlib.sha256(card_id.encode()).hexdigest()

# Simulación de procesamiento de pagos (reemplazar con integración real de PayPal)
def process_payment(amount, payment_method):
    return {"status": "success", "transaction_id": f"TRANS{random.randint(1000, 9999)}"}

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        cedula = request.form['cedula']
        email = request.form['email']
        phone = request.form['phone']
        db = get_db()
        cursor = db.cursor()
        try:
            cursor.execute('INSERT INTO users (cedula, email, phone) VALUES (%s, %s, %s)', (cedula, email, phone))
            db.commit()
            flash('¡Registro exitoso! Por favor, inicia sesión.')
            return redirect(url_for('login'))
        except:
            flash('Error: El usuario ya existe o los datos son inválidos.')
        finally:
            cursor.close()
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        db = get_db()
        cursor = db.cursor()
        cursor.execute('SELECT * FROM users WHERE email = %s', (email,))
        user = cursor.fetchone()
        cursor.close()
        if user:
            otp = generate_otp()
            session['otp'] = otp
            session['email'] = email
            print(f"OTP para {email}: {otp}")  # En producción, enviar por correo/SMS
            flash('Se envió un OTP a tu correo/teléfono. Por favor, ingrésalo.')
            return redirect(url_for('verify_otp'))
        flash('Correo no encontrado.')
    return render_template('login.html')

@app.route('/verify_otp', methods=['GET', 'POST'])
def verify_otp():
    if request.method == 'POST':
        user_otp = request.form['otp']
        if 'otp' in session and user_otp == session['otp']:
            email = session['email']
            db = get_db()
            cursor = db.cursor()
            cursor.execute('SELECT * FROM users WHERE email = %s', (email,))
            user = cursor.fetchone()
            cursor.close()
            session['user_id'] = user[0]
            session.pop('otp', None)
            session.pop('email', None)
            flash('¡Inicio de sesión exitoso!')
            return redirect(url_for('dashboard'))
        flash('OTP inválido.')
    return render_template('login.html', verify_otp=True)

@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    db = get_db()
    cursor = db.cursor()
    cursor.execute('SELECT * FROM users WHERE id = %s', (session['user_id'],))
    user = cursor.fetchone()
    cursor.execute('SELECT * FROM cards WHERE user_id = %s', (session['user_id'],))
    cards = cursor.fetchall()
    cursor.close()
    return render_template('dashboard.html', user=user, cards=cards)

@app.route('/add_card', methods=['GET', 'POST'])
def add_card():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    if request.method == 'POST':
        card_id = request.form['card_id']
        hashed_card_id = hash_card_id(card_id)
        db = get_db()
        cursor = db.cursor()
        try:
            cursor.execute('INSERT INTO cards (user_id, card_id, balance) VALUES (%s, %s, %s)', 
                           (session['user_id'], hashed_card_id, 0.0))
            db.commit()
            flash('¡Tarjeta agregada exitosamente!')
            return redirect(url_for('dashboard'))
        except:
            flash('Error: La tarjeta ya existe o el ID es inválido.')
        finally:
            cursor.close()
    return render_template('add_card.html')

@app.route('/recharge/<card_id>', methods=['GET', 'POST'])
def recharge(card_id):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    db = get_db()
    cursor = db.cursor()
    cursor.execute('SELECT * FROM cards WHERE card_id = %s AND user_id = %s', (card_id, session['user_id']))
    card = cursor.fetchone()
    if not card:
        cursor.close()
        flash('Tarjeta no encontrada.')
        return redirect(url_for('dashboard'))
    if request.method == 'POST':
        amount = float(request.form['amount'])
        payment_method = request.form['payment_method']
        if amount % 20 != 0:
            cursor.close()
            flash('El monto debe ser múltiplo de RD$20.')
            return redirect(url_for('recharge', card_id=card_id))
        payment_result = process_payment(amount, payment_method)
        if payment_result['status'] == 'success':
            cursor.execute('UPDATE cards SET balance = balance + %s WHERE card_id = %s', (amount, card_id))
            cursor.execute('INSERT INTO transactions (user_id, card_id, amount, payment_method, transaction_id, status, created_at) VALUES (%s, %s, %s, %s, %s, %s, %s)',
                           (session['user_id'], card_id, amount, payment_method, payment_result['transaction_id'], 'completed', datetime.utcnow()))
            db.commit()
            flash('¡Recarga exitosa!')
            cursor.close()
            return redirect(url_for('dashboard'))
        flash('El pago falló.')
    cursor.close()
    return render_template('recharge.html', card=card)

@app.route('/history')
def history():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    db = get_db()
    cursor = db.cursor()
    cursor.execute('SELECT t.*, c.card_id FROM transactions t JOIN cards c ON t.card_id = c.card_id WHERE t.user_id = %s ORDER BY t.created_at DESC',
                   (session['user_id'],))
    transactions = cursor.fetchall()
    cursor.close()
    return render_template('history.html', transactions=transactions)

@app.route('/balance')
def balance():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    db = get_db()
    cursor = db.cursor()
    cursor.execute('SELECT * FROM cards WHERE user_id = %s', (session['user_id'],))
    cards = cursor.fetchall()
    cursor.close()
    return render_template('balance.html', cards=cards)

@app.route('/logout')
def logout():
    session.clear()
    flash('Sesión cerrada exitosamente.')
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=True)
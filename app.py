from flask import Flask, render_template, request, jsonify, redirect, url_for
import sqlite3
import json
from datetime import datetime
from agent import evaluate_transaction

app = Flask(__name__)

def get_db_connection():
    conn = sqlite3.connect('transactions.db')
    conn.row_factory = sqlite3.Row
    return conn

@app.route('/')
def dashboard():
    conn = get_db_connection()
    # Simply read transactions with their stored status from the database
    transactions = conn.execute('''
        SELECT * FROM transactions 
        ORDER BY Date DESC, Time DESC
    ''').fetchall()
    conn.close()
    
    return render_template('dashboard.html', transactions=transactions)

@app.route('/new-transaction', methods=['GET', 'POST'])
def new_transaction():
    if request.method == 'GET':
        return render_template('new_transaction.html')
    
    # Process new transaction
    txn_data = {
        "CustomerID": request.form['sender'],
        "CustomerID2": request.form['receiver'],
        "Amount": float(request.form['amount']),
        "Date": request.form['date'],
        "Time": request.form['time'],
        "IP": request.form['ip']
    }
    
    # THIS IS WHERE WE EVALUATE - only for new transactions
    result = evaluate_transaction(txn_data)
    
    # Extract status and explanation
    status = "normal"
    if "Send Slack alert" in result:
        status = "alert"  # Red
    elif "Flag to admin" in result:
        status = "flag"   # Yellow
    
    # Get the explanation part
    explanation = result.split("\n\nSystem:")[0] if "\n\nSystem:" in result else result
    
    # Save to database with the evaluation result
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
    'INSERT INTO transactions (CustomerID, CustomerID2, Amount, Date, Time, IP, status, explanation) VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
    (txn_data["CustomerID"], txn_data["CustomerID2"], txn_data["Amount"], 
     txn_data["Date"], txn_data["Time"], txn_data["IP"], status, explanation)
)
    txn_id = cursor.lastrowid
    conn.commit()
    conn.close()
    
    return redirect(url_for('transaction_detail', txn_id=txn_id))

@app.route('/transaction/<txn_id>')
def transaction_detail(txn_id):
    conn = get_db_connection()
    transaction = conn.execute('SELECT * FROM transactions WHERE ID = ?', 
                          (txn_id,)).fetchone()
    conn.close()
    
    if transaction is None:
        return "Transaction not found", 404
        
    return render_template('transaction_detail.html', transaction=transaction)

if __name__ == '__main__':
    # Make sure new DB columns exist
    conn = get_db_connection()
    try:
        conn.execute('ALTER TABLE transactions ADD COLUMN status TEXT DEFAULT "normal"')
        conn.execute('ALTER TABLE transactions ADD COLUMN explanation TEXT')
        conn.commit()
    except sqlite3.OperationalError:
        # Columns already exist
        pass
    conn.close()
    
    app.run(debug=True)
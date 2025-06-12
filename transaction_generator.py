# transaction_generator.py
import random
import time
import requests
from datetime import datetime, timedelta
from itertools import cycle

# Configuration
API_URL = "http://localhost:8000/detect"
SEND_INTERVAL = 0.5  # seconds between transactions
DAYS_TO_SIMULATE = 30
CIRCULAR_INTERVAL = (10, 30)  # min/max seconds between circular patterns

# Sample data
employees = [f"emp_{i}" for i in range(1, 11)]
customers = [f"cust_{chr(i)}" for i in range(65, 75)]  # A-J

def generate_normal_transaction():
    """Generate random legitimate transaction"""
    return {
        "transaction_id": f"tx_{int(time.time())}_{random.randint(1000,9999)}",
        "employee_id": random.choice(employees),
        "customer_id": random.choice(customers),
        "amount": random.randint(100, 5000),
        "timestamp": datetime.now().isoformat()
    }

def generate_suspicious_transaction():
    """Generate transactions that should trigger collusion alerts"""
    emp = random.choice(employees[:3])
    cust = random.choice(customers[:3])
    
    patterns = [
        {"amount": random.randint(8000, 9500)},
        {"amount": 10000, "employee_id": emp},
        {"customer_id": cust, "employee_id": emp}
    ]
    
    return {
        **{
            "transaction_id": f"susp_{int(time.time())}_{random.randint(1000,9999)}",
            "timestamp": datetime.now().isoformat(),
            "risk_score": random.uniform(0.6, 0.9)
        },
        **random.choice(patterns)
    }

def generate_circular_transactions():
    """Generate a set of circular transactions (3 transactions that form a loop)"""
    # Select 3 distinct employees and customers for the cycle
    cycle_emps = random.sample(employees[:5], 3)
    cycle_custs = random.sample(customers[:5], 3)
    
    # Create a circular pattern: emp1 -> cust1 -> emp2 -> cust2 -> emp3 -> cust3 -> emp1
    transactions = []
    base_amount = random.randint(5000, 15000)
    
    for i in range(3):
        tx = {
            "transaction_id": f"circ_{int(time.time())}_{random.randint(1000,9999)}_{i}",
            "employee_id": cycle_emps[i],
            "customer_id": cycle_custs[i],
            "amount": base_amount + random.randint(-500, 500),
            "timestamp": datetime.now().isoformat(),
            "risk_score": random.uniform(0.7, 0.95)
        }
        transactions.append(tx)
    
    return transactions

def send_transaction(tx):
    try:
        response = requests.post(API_URL, json=tx)
        print(f"Sent {tx['transaction_id']} - Status: {response.status_code}")
        if response.json().get('alerts'):
            print("🚨 ALERT:", response.json()['alerts'])
    except Exception as e:
        print(f"Error sending transaction: {e}")

def simulate_historical_data(days):
    """Generate transactions spread over historical period"""
    now = datetime.now()
    for day in range(days, 0, -1):
        date = now - timedelta(days=day)
        
        # Normal daily transactions
        for _ in range(random.randint(50, 100)):
            tx = generate_normal_transaction()
            tx["timestamp"] = date.isoformat()
            send_transaction(tx)
            time.sleep(0.1)
        
        # Occasional suspicious activity
        if day % 3 == 0:
            for _ in range(random.randint(3, 5)):
                tx = generate_suspicious_transaction()
                tx["timestamp"] = date.isoformat()
                send_transaction(tx)
                time.sleep(0.1)
            
            # Add circular transactions occasionally
            if random.random() < 0.3:
                for tx in generate_circular_transactions():
                    tx["timestamp"] = date.isoformat()
                    send_transaction(tx)
                    time.sleep(0.2)

def real_time_stream():
    """Simulate live transaction stream with occasional circular patterns"""
    last_circular = time.time()
    next_circular = random.uniform(*CIRCULAR_INTERVAL)
    
    while True:
        current_time = time.time()
        
        # Check if it's time for circular transactions
        if current_time - last_circular > next_circular:
            print("\n🔵 Generating circular transaction pattern")
            for tx in generate_circular_transactions():
                send_transaction(tx)
                time.sleep(0.3)
            
            last_circular = current_time
            next_circular = random.uniform(*CIRCULAR_INTERVAL)
        
        # Regular transaction flow
        tx = generate_suspicious_transaction() if random.random() < 0.1 else generate_normal_transaction()
        send_transaction(tx)
        time.sleep(SEND_INTERVAL)

if __name__ == "__main__":
    print("=== Generating historical data ===")
    simulate_historical_data(DAYS_TO_SIMULATE)
    
    print("\n=== Starting real-time stream with circular transactions ===")
    real_time_stream()
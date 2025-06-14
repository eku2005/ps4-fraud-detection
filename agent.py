import sqlite3
from datetime import datetime
from langchain.vectorstores import FAISS
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain.docstore.document import Document
from langchain_groq import ChatGroq
from langchain.chains import RetrievalQA
import os
import requests
import json
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# SlackReporter class for fraud alerts
class SlackReporter:
    def __init__(self):
        self.webhook_url = os.getenv("SLACK_WEBHOOK_URL")
        self.bot_token = os.getenv("SLACK_BOT_TOKEN")
        self.default_channel = os.getenv("SLACK_DEFAULT_CHANNEL", "fraud-alerts")
    
    def send_alert(self, transaction_data, analysis):
        """Send formatted fraud alert to Slack"""
        if not self.webhook_url and not self.bot_token:
            print("Slack credentials not configured. Would have sent a Slack alert.")
            return {"error": "Slack credentials not configured"}
        
        # Format the alert blocks for Slack
        blocks = self._format_alert_blocks(transaction_data, analysis)
        
        # Use appropriate sending method
        if self.bot_token:
            return self._send_with_bot(blocks, self.default_channel)
        else:
            return self._send_with_webhook(blocks)
    
    def _send_with_bot(self, blocks, channel):
        """Send message using Slack Bot API"""
        headers = {
            "Authorization": f"Bearer {self.bot_token}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "channel": channel,
            "text": "🚨 FRAUD ALERT",
            "blocks": blocks
        }
        
        response = requests.post(
            "https://slack.com/api/chat.postMessage",
            headers=headers,
            data=json.dumps(payload)
        )
        
        return response.json()
    
    def _send_with_webhook(self, blocks):
        """Send message using Slack Webhook"""
        payload = {
            "text": "🚨 FRAUD ALERT",
            "blocks": blocks
        }
        
        response = requests.post(
            self.webhook_url,
            data=json.dumps(payload),
            headers={'Content-Type': 'application/json'}
        )
        
        return {"status": response.status_code, "text": response.text}
    
    def _format_alert_blocks(self, transaction_data, analysis):
        """Format fraud alert data into Slack blocks"""
        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": "🚨 FRAUD ALERT: Suspicious Transaction",
                    "emoji": True
                }
            },
            {
                "type": "section",
                "fields": [
                    {
                        "type": "mrkdwn",
                        "text": f"*Customer:*\n{transaction_data['CustomerID']}"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Recipient:*\n{transaction_data['CustomerID2']}"
                    }
                ]
            },
            {
                "type": "section",
                "fields": [
                    {
                        "type": "mrkdwn",
                        "text": f"*Amount:*\n${transaction_data['Amount']}"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Date/Time:*\n{transaction_data['Date']} at {transaction_data['Time']}"
                    }
                ]
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*IP Address:*\n{transaction_data['IP']}"
                }
            },
            {
                "type": "divider"
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "*AI Analysis:*\n" + analysis
                }
            }
        ]
        
        return blocks

# Define action tools
class FraudDetectionTools:
    def __init__(self):
        self.slack_reporter = SlackReporter()
    
    def send_slack_alert(self, transaction_data, analysis):
        """Send a Slack alert for highly suspicious transactions"""
        print(f"\n🚨 SENDING SLACK ALERT 🚨")
        print(f"Transaction: {transaction_data['CustomerID']} to {transaction_data['CustomerID2']} for ${transaction_data['Amount']}")
        
        # Try to send to Slack if credentials are available
        self.slack_reporter.send_alert(transaction_data, analysis)
        return "Slack alert sent for suspicious transaction."
    
    def flag_to_admin(self, transaction_data, analysis):
        """Flag a transaction to admin for review"""
        print(f"\n⚠️ FLAGGING TO ADMIN FOR REVIEW ⚠️")
        print(f"Transaction: {transaction_data['CustomerID']} to {transaction_data['CustomerID2']} for ${transaction_data['Amount']}")
        return "Transaction flagged to admin for review."

# Set API key
os.environ["GROQ_API_KEY"] = "..."

# Step 1: Load previous transactions from SQLite
conn = sqlite3.connect("transactions.db")
cursor = conn.cursor()
# Fixed column names to match database schema
cursor.execute("SELECT ID, CustomerID, CustomerID2, Amount, Date, Time, IP FROM transactions")
rows = cursor.fetchall()
conn.close()

print(f"Total transactions loaded from database: {len(rows)}")
customer_counts = {}
for row in rows:
    customer_id = row[1]  # CustomerID is at index 1
    customer_counts[customer_id] = customer_counts.get(customer_id, 0) + 1

print(f"Transactions per customer:")
for customer, count in customer_counts.items():
    print(f"- {customer}: {count} transactions")
    
# Step 2: Convert transactions to documents
docs = []
for row in rows:
    # Match variable names with actual column names
    txn_id, customer_id, customer_id2, amount, date, time, ip = row
    content = (
        f"Transaction by {customer_id} to {customer_id2} of ${amount} on {date} at {time} from IP {ip}."
    )
    docs.append(Document(page_content=content, metadata={"txn_id": txn_id, "customer_id": customer_id}))
# Step 3: Embed the documents using HuggingFaceEmbeddings
embeddings = HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2")
vectorstore = FAISS.from_documents(docs, embeddings)
general_retriever = vectorstore.as_retriever(search_kwargs={"k": 5})

# Step 4: Use Groq + LLaMA 3
llm = ChatGroq(model_name="llama3-70b-8192", temperature=0.2)
qa_chain = RetrievalQA.from_chain_type(llm=llm, retriever=general_retriever)

# Initialize tools
tools = FraudDetectionTools()

# Step 5: Define the agent evaluation function with actions
def evaluate_transaction(new_txn):
    customer_id = new_txn['CustomerID']
    
    # Create customer-specific retriever with metadata filtering
    customer_retriever = vectorstore.as_retriever(
        search_kwargs={
            "k": 5,
            "filter": {"customer_id": customer_id}  # Only retrieve this customer's transactions
        }
    )
    
    # Create a customer-specific chain
    customer_qa_chain = RetrievalQA.from_chain_type(llm=llm, retriever=customer_retriever)
    prompt = f"""
You are a fraud detection agent. A new transaction has occurred:

CustomerID: {new_txn['CustomerID']}
To: {new_txn['CustomerID2']}
Amount: ${new_txn['Amount']}
Date: {new_txn['Date']}
Time: {new_txn['Time']}
IP Address: {new_txn['IP']}

Based on the customer's historical behavior, evaluate if this transaction is normal or suspicious.

IMPORTANT: First provide a detailed analysis explaining your reasoning. Then determine the appropriate action by concluding with one of these exact phrases:
- "ACTION: No action required" - If transaction is within normal patterns
- "ACTION: Flag to admin" - If transaction shows slight deviation from normal patterns
- "ACTION: Send Slack alert" - If transaction shows strong anomalies

Your analysis must clearly explain the factors that led to your decision.
"""

    response = customer_qa_chain.run(prompt)
    
    # Extract the analysis part (everything before the ACTION line)
    analysis_parts = response.split("ACTION:")
    analysis = analysis_parts[0].strip()
    
    # Determine which action to take
    if "Send Slack alert" in response:
        action_result = tools.send_slack_alert(new_txn, analysis)
    elif "Flag to admin" in response:
        action_result = tools.flag_to_admin(new_txn, analysis)
    else:
        action_result = "No action required for this transaction."
    
    # Return the full response with analysis and action taken
    return f"{response}\n\nSystem: {action_result}"

# Step 6: Test Anomalous Transaction
# test_txn = {
#     "CustomerID": "CUST007",
#     "CustomerID2": "CUST002",
#     "Amount": 15000,
#     "Date": "2025-05-12",
#     "Time": "13:00",
#     "IP": "192.168.1.8"
# }

# print(evaluate_transaction(test_txn))

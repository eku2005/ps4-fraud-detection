# collusion_app.py
from fastapi import FastAPI
from pydantic import BaseModel
import sqlite3
import networkx as nx
from datetime import datetime
import pandas as pd
import dash
from dash import dcc, html, Input, Output
import plotly.express as px
import plotly.graph_objects as go
import uvicorn
from threading import Thread
from typing import List, Dict, Any

# Database Setup
conn = sqlite3.connect('collusion.db', check_same_thread=False)
c = conn.cursor()

c.execute('''CREATE TABLE IF NOT EXISTS transactions
             (id TEXT PRIMARY KEY, employee_id TEXT, customer_id TEXT, 
              amount REAL, timestamp TEXT, risk_score REAL, is_collusion INTEGER)''')

c.execute('''CREATE TABLE IF NOT EXISTS relationships
             (id TEXT PRIMARY KEY, employee_id TEXT, customer_id TEXT, 
              strength REAL, last_updated TEXT)''')
conn.commit()

# Detection Engine
class CollusionDetector:
    def __init__(self):
        self.graph = nx.Graph()
        self.load_existing_data()
    
    def load_existing_data(self):
        for row in c.execute('SELECT * FROM transactions'):
            self._update_graph(row)
    
    def process_transaction(self, tx_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        c.execute('''INSERT OR REPLACE INTO transactions VALUES 
                     (?, ?, ?, ?, ?, ?, ?)''',
                  (tx_data['transaction_id'], tx_data['employee_id'], 
                   tx_data['customer_id'], tx_data['amount'], 
                   tx_data['timestamp'], tx_data.get('risk_score', 0), 0))
        
        tx = (tx_data['transaction_id'], tx_data['employee_id'], 
              tx_data['customer_id'], tx_data['amount'], tx_data['timestamp'])
        self._update_graph(tx)
        
        alerts = self._run_detection(tx_data)
        if alerts:
            c.execute('UPDATE transactions SET is_collusion=1 WHERE id=?', 
                      (tx_data['transaction_id'],))
        
        conn.commit()
        return alerts
    
    def _update_graph(self, tx: tuple):
        emp_id, cust_id = tx[1], tx[2]
        
        if self.graph.has_edge(emp_id, cust_id):
            self.graph[emp_id][cust_id]['weight'] += 1
        else:
            self.graph.add_edge(emp_id, cust_id, weight=1)
        
        max_weight = max((d['weight'] for _, _, d in self.graph.edges(data=True)), default=1)
        strength = self.graph[emp_id][cust_id]['weight'] / max_weight
        
        c.execute('''INSERT OR REPLACE INTO relationships VALUES 
                     (?, ?, ?, ?, ?)''',
                  (f"{emp_id}-{cust_id}", emp_id, cust_id, 
                   strength, datetime.now().isoformat()))
    
    def _run_detection(self, tx_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        emp_id, cust_id = tx_data['employee_id'], tx_data['customer_id']
        alerts = []
        
        # Relationship strength detection
        neighbors = list(self.graph.neighbors(emp_id))
        if neighbors:
            this_strength = self.graph[emp_id][cust_id]['weight']
            avg_strength = sum(self.graph[emp_id][n]['weight'] for n in neighbors) / len(neighbors)
            if this_strength > 3 * avg_strength:
                alerts.append({
                    'rule': 'UNUSUAL_RELATIONSHIP_STRENGTH',
                    'confidence': min(0.99, this_strength / (avg_strength + 1))
                })
        
        # Circular transactions detection
        try:
            if len(nx.find_cycle(self.graph, cust_id)) >= 3:
                alerts.append({'rule': 'CIRCULAR_TRANSACTIONS', 'confidence': 0.85})
        except nx.NetworkXNoCycle:
            pass
        
        return alerts

    def get_circular_transactions(self) -> pd.DataFrame:
        query = '''
            SELECT t1.id as tx1, t2.id as tx2, t3.id as tx3,
                   t1.employee_id as emp1, t2.employee_id as emp2,
                   t1.customer_id as cust1, t2.customer_id as cust2, t3.customer_id as cust3,
                   t1.timestamp as time1, t2.timestamp as time2, t3.timestamp as time3,
                   t1.amount as amt1, t2.amount as amt2, t3.amount as amt3
            FROM transactions t1
            JOIN transactions t2 ON t1.customer_id = t2.employee_id
            JOIN transactions t3 ON t2.customer_id = t3.employee_id AND t3.customer_id = t1.employee_id
            WHERE t1.is_collusion = 1 AND t2.is_collusion = 1 AND t3.is_collusion = 1
            ORDER BY t1.timestamp DESC
            LIMIT 5
        '''
        return pd.read_sql(query, conn)

# Web API
app = FastAPI()
detector = CollusionDetector()

class TransactionInput(BaseModel):
    transaction_id: str
    employee_id: str
    customer_id: str
    amount: float
    timestamp: str
    risk_score: float = 0.0

@app.post("/detect")
async def detect_collusion(tx: TransactionInput):
    alerts = detector.process_transaction(tx.dict())
    return {
        "transaction_id": tx.transaction_id,
        "alerts": alerts,
        "status": "flagged" if alerts else "clean"
    }

# Minimalist Dashboard
def run_dashboard():
    dash_app = dash.Dash(__name__, assets_folder='assets')
    
    # CSS styles
    styles = {
        'container': {
            'fontFamily': 'Arial, sans-serif',
            'maxWidth': '1200px',
            'margin': '0 auto',
            'padding': '20px',
            'backgroundColor': '#f8f9fa'
        },
        'header': {
            'textAlign': 'center',
            'marginBottom': '30px',
            'color': '#2c3e50'
        },
        'card': {
            'backgroundColor': 'white',
            'borderRadius': '8px',
            'padding': '20px',
            'marginBottom': '20px',
            'boxShadow': '0 2px 4px rgba(0,0,0,0.05)'
        },
        'metric': {
            'display': 'flex',
            'justifyContent': 'space-between',
            'marginBottom': '15px'
        },
        'alert': {
            'color': '#e74c3c',
            'fontWeight': 'bold'
        },
        'streamItem': {
            'padding': '8px 0',
            'borderBottom': '1px solid #eee',
            'fontSize': '14px'
        }
    }
    
    dash_app.layout = html.Div(style=styles['container'], children=[
        html.H1("Fraud Detection Monitor", style=styles['header']),
        
        # Metrics
        html.Div(style=styles['card'], children=[
            html.Div(style={'display': 'flex', 'justifyContent': 'space-around'}, children=[
                html.Div([
                    html.Div("Total Transactions", style={'color': '#7f8c8d', 'fontSize': '14px'}),
                    html.Div(id='transaction-count', style={'fontSize': '24px', 'fontWeight': 'bold'})
                ]),
                html.Div([
                    html.Div("Alerts", style={'color': '#7f8c8d', 'fontSize': '14px'}),
                    html.Div(id='alert-count', style={'fontSize': '24px', 'fontWeight': 'bold', 'color': '#e74c3c'})
                ]),
                html.Div([
                    html.Div("Last Alert", style={'color': '#7f8c8d', 'fontSize': '14px'}),
                    html.Div(id='last-alert', style={'fontSize': '16px'})
                ])
            ])
        ]),
        
        # Main Content
        html.Div([
            # Left Column
            html.Div([
                html.Div(style=styles['card'], children=[
                    dcc.Graph(id='relationship-graph', style={'height': '400px'})
                ]),
                html.Div(style=styles['card'], children=[
                    dcc.Graph(id='circular-transactions-graph', style={'height': '300px'})
                ])
            ], style={'width': '48%', 'display': 'inline-block', 'verticalAlign': 'top'}),
            
            # Right Column
            html.Div([
                html.Div(style=styles['card'], children=[
                    html.Div("Recent Alerts", style={'marginBottom': '10px', 'fontWeight': 'bold'}),
                    dash.dash_table.DataTable(
                        id='alerts-table',
                        columns=[
                            {'name': 'Time', 'id': 'timestamp'},
                            {'name': 'Transaction', 'id': 'transaction_id'},
                            {'name': 'Amount', 'id': 'amount'},
                            {'name': 'Parties', 'id': 'parties'}
                        ],
                        style_table={'overflowX': 'auto'},
                        style_cell={
                            'padding': '8px',
                            'textAlign': 'left',
                            'border': 'none',
                            'fontSize': '14px'
                        },
                        style_header={
                            'backgroundColor': 'transparent',
                            'fontWeight': 'bold',
                            'borderBottom': '1px solid #eee'
                        },
                        style_data_conditional=[{
                            'if': {'row_index': 'odd'},
                            'backgroundColor': 'rgba(245, 245, 245, 0.5)'
                        }]
                    )
                ]),
                
                html.Div(style=styles['card'], children=[
                    html.Div("Activity Stream", style={'marginBottom': '10px', 'fontWeight': 'bold'}),
                    html.Div(id='transaction-stream', style={
                        'height': '300px',
                        'overflowY': 'scroll',
                        'padding': '5px'
                    })
                ])
            ], style={'width': '48%', 'display': 'inline-block', 'marginLeft': '4%', 'verticalAlign': 'top'})
        ]),
        
        dcc.Interval(id='interval-component', interval=2000, n_intervals=0)
    ])

    @dash_app.callback(
        [Output('relationship-graph', 'figure'),
         Output('transaction-stream', 'children'),
         Output('alerts-table', 'data'),
         Output('transaction-count', 'children'),
         Output('alert-count', 'children'),
         Output('last-alert', 'children'),
         Output('circular-transactions-graph', 'figure')],
        [Input('interval-component', 'n_intervals')]
    )
    def update_dashboard(n):
        # Get data
        relationships = pd.read_sql('SELECT * FROM relationships', conn)
        transactions = pd.read_sql('SELECT * FROM transactions ORDER BY timestamp DESC LIMIT 50', conn)
        alerts = pd.read_sql('SELECT * FROM transactions WHERE is_collusion=1 ORDER BY timestamp DESC LIMIT 10', conn)
        circular_tx = detector.get_circular_transactions()

        # 1. Relationship Graph
        rel_fig = px.scatter(
            relationships,
            x='employee_id',
            y='customer_id',
            size='strength',
            color='strength',
            color_continuous_scale='Blues',
            title=""
        )
        rel_fig.update_layout(
            margin={'l': 30, 'r': 30, 't': 30, 'b': 30},
            plot_bgcolor='rgba(0,0,0,0)',
            paper_bgcolor='rgba(0,0,0,0)',
            xaxis_title="",
            yaxis_title=""
        )

        # 2. Transaction Stream
        tx_stream = [
            html.Div([
                html.Span(f"{tx['timestamp'][11:19]} ", style={'color': '#95a5a6'}),
                html.Span(f"${tx['amount']:,.2f} ", style={'color': '#e74c3c' if tx['is_collusion'] else '#2c3e50'}),
                html.Span(f"{tx['employee_id']} → {tx['customer_id']}")
            ], style={**styles['streamItem'], 
                      'color': '#e74c3c' if tx['is_collusion'] else '#2c3e50'})
            for _, tx in transactions.iterrows()
        ]

        # 3. Alerts Table
        alerts_data = [{
            'timestamp': alert['timestamp'][11:19],
            'transaction_id': alert['id'][:8] + "...",
            'amount': f"${alert['amount']:,.2f}",
            'parties': f"{alert['employee_id']} ↔ {alert['customer_id']}"
        } for _, alert in alerts.iterrows()]

        # 4. Circular Transactions Graph
        if not circular_tx.empty:
            circ_fig = go.Figure()
            for _, circ in circular_tx.iterrows():
                circ_fig.add_trace(go.Scatter(
                    x=[circ['time1'], circ['time2'], circ['time3']],
                    y=[circ['amt1'], circ['amt2'], circ['amt3']],
                    mode='lines+markers',
                    line=dict(color='#e74c3c', width=2),
                    marker=dict(size=8)
                ))
            circ_fig.update_layout(
                margin={'l': 40, 'r': 30, 't': 30, 'b': 40},
                plot_bgcolor='rgba(0,0,0,0)',
                paper_bgcolor='rgba(0,0,0,0)',
                showlegend=False
            )
        else:
            circ_fig = go.Figure()
            circ_fig.update_layout(
                plot_bgcolor='rgba(0,0,0,0)',
                paper_bgcolor='rgba(0,0,0,0)',
                annotations=[dict(
                    text="No circular transactions",
                    showarrow=False,
                    x=0.5, y=0.5,
                    xref="paper", yref="paper"
                )]
            )

        # Metrics
        tx_count = c.execute('SELECT COUNT(*) FROM transactions').fetchone()[0]
        alert_count = c.execute('SELECT COUNT(*) FROM transactions WHERE is_collusion=1').fetchone()[0]
        last_alert = alerts.iloc[0]['timestamp'][11:19] if not alerts.empty else "None"

        return (
            rel_fig,
            tx_stream,
            alerts_data,
            f"{tx_count:,}",
            f"{alert_count:,}",
            last_alert if last_alert != "None" else "No alerts",
            circ_fig
        )

    dash_app.run(port=8050)

if __name__ == "__main__":
    Thread(target=run_dashboard, daemon=True).start()
    uvicorn.run(app, host="0.0.0.0", port=8000)
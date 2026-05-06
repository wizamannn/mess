import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime, timedelta
import os
import cv2
import numpy as np
import io
from fpdf import FPDF

# --- 1. CLOUD-COMPATIBLE DIRECTORY SETUP ---
# We use /tmp/ because it's the only place Streamlit Cloud lets us write files
IS_CLOUD = os.path.exists("/mount")

if IS_CLOUD:
    STAFF_ID_DIR = "/tmp/staff_ids"
    DAILY_LOG_BASE = "/tmp/logs"
    DB_PATH = "/tmp/business.db"
else:
    STAFF_ID_DIR = "staff_ids"
    DAILY_LOG_BASE = "logs"
    DB_PATH = "business.db"

# Create folders safely
for folder in [STAFF_ID_DIR, DAILY_LOG_BASE]:
    try:
        if not os.path.exists(folder):
            os.makedirs(folder, exist_ok=True)
    except Exception:
        pass # Ignore errors to prevent white screen

# --- 2. DATABASE LOGIC ---
try:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (username TEXT PRIMARY KEY, password TEXT, role TEXT, status TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS attendance (username TEXT, timestamp TEXT, action TEXT, photo_path TEXT)''')
    
    # Default Admin
    c.execute("SELECT * FROM users WHERE username='admin'")
    if not c.fetchone():
        c.execute("INSERT INTO users VALUES ('admin', 'admin123', 'employer', 'approved')")
        conn.commit()
except Exception as e:
    st.error(f"Database Error: {e}")

# --- 3. BUSINESS LOGIC ---
def get_weekly_stats(df):
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    now = datetime.now()
    start_of_week = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0)
    
    report = []
    week_data = df[df['timestamp'] >= start_of_week].sort_values(['username', 'timestamp'])
    for user in week_data['username'].unique():
        user_logs = week_data[week_data['username'] == user]
        total_sec, last_in = 0, None
        for _, row in user_logs.iterrows():
            if row['action'] == 'IN': last_in = row['timestamp']
            elif row['action'] == 'OUT' and last_in:
                total_sec += (row['timestamp'] - last_in).total_seconds()
                last_in = None
        hours = round(total_sec / 3600, 2)
        report.append({"Employee": user, "Hours": hours, "Pay ($15/hr)": round(hours * 15, 2)})
    return pd.DataFrame(report), start_of_week

# --- 4. APP INTERFACE ---
st.set_page_config(page_title="Walia Management", layout="wide")

if 'logged_in' not in st.session_state:
    st.session_state.update({'logged_in': False, 'user': None, 'role': None})

if not st.session_state['logged_in']:
    st.markdown("<h1 style='text-align: center;'>ENTER PIN</h1>", unsafe_allow_html=True)
    col1, col2, col3 = st.columns([1,1,1])
    with col2:
        pin = st.text_input("PIN", type="password", label_visibility="collapsed")
        if st.button("LOG IN", use_container_width=True):
            c.execute('SELECT role, status, username FROM users WHERE password = ?', (pin,))
            res = c.fetchone()
            if res and (res[1] == 'approved' or res[0] == 'employer'):
                st.session_state.update({'logged_in': True, 'user': res[2], 'role': res[0]})
                st.rerun()
            else: st.error("Access Denied.")

else:
    st.sidebar.button("EXIT", on_click=lambda: st.session_state.update({'logged_in': False}))

    if st.session_state['role'] == 'employee':
        st.header(f"Employee: {st.session_state['user']}")
        cam = st.camera_input("Verify Identity")
        if cam:
            c1, c2 = st.columns(2)
            ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            if c1.button("CLOCK IN"):
                c.execute("INSERT INTO attendance VALUES (?, ?, 'IN', 'WEB')", (st.session_state['user'], ts))
                conn.commit(); st.success("In")
            if c2.button("CLOCK OUT"):
                c.execute("INSERT INTO attendance VALUES (?, ?, 'OUT', 'WEB')", (st.session_state['user'], ts))
                conn.commit(); st.info("Out")

    elif st.session_state['role'] == 'employer':
        st.title("MANAGER MENU")
        t1, t2, t3 = st.tabs(["Employees", "Logs", "Payroll"])
        
        with t2:
            st.subheader("Add Missing Punch")
            staff_list = [r[0] for r in c.execute("SELECT username FROM users WHERE role='employee'").fetchall()]
            if staff_list:
                e_name = st.selectbox("Employee", staff_list)
                e_date = st.date_input("Date")
                e_time = st.time_input("Time")
                e_action = st.selectbox("Action", ["IN", "OUT"])
                if st.button("Save Entry"):
                    c.execute("INSERT INTO attendance VALUES (?, ?, ?, 'MANUAL')", (e_name, f"{e_date} {e_time}", e_action))
                    conn.commit(); st.rerun()
            
            logs = pd.read_sql_query("SELECT * FROM attendance ORDER BY timestamp DESC", conn)
            st.dataframe(logs, use_container_width=True)
        
        with t3:
            df_all = pd.read_sql_query("SELECT * FROM attendance", conn)
            if not df_all.empty:
                stats, week_start = get_weekly_stats(df_all)
                st.dataframe(stats)
                # Simple Excel Export
                excel_buf = io.BytesIO()
                with pd.ExcelWriter(excel_buf, engine='xlsxwriter') as writer:
                    stats.to_excel(writer, index=False)
                st.download_button("📥 Export Excel", excel_buf.getvalue(), "Payroll.xlsx")
            else:
                st.info("No logs found.")

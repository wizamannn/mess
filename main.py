import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime, timedelta
import os
import cv2
import numpy as np
import io

# --- 1. DIRECTORY SETUP ---
STAFF_ID_DIR = "permanent_staff_ids"
DAILY_LOG_BASE = "attendance_photos"
for folder in [STAFF_ID_DIR, DAILY_LOG_BASE]:
    if not os.path.exists(folder): os.makedirs(folder)

face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')

# --- 2. DATABASE LOGIC ---
conn = sqlite3.connect('company_data.db', check_same_thread=False)
c = conn.cursor()
c.execute('''CREATE TABLE IF NOT EXISTS users (username TEXT PRIMARY KEY, password TEXT, role TEXT, status TEXT)''')
c.execute('''CREATE TABLE IF NOT EXISTS attendance (username TEXT, timestamp TEXT, action TEXT, photo_path TEXT)''')

# Default Admin Login
c.execute("SELECT * FROM users WHERE username='admin'")
if not c.fetchone():
    c.execute("INSERT INTO users VALUES ('admin', 'admin123', 'employer', 'approved')")
    conn.commit()

# --- 3. PAYROLL LOGIC ---
def get_payroll_report(df):
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    now = datetime.now()
    start_of_week = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0)
    start_of_year = now.replace(month=1, day=1, hour=0, minute=0, second=0)

    report = []
    for user in df['username'].unique():
        user_data = df[df['username'] == user].sort_values('timestamp')
        def calc_hours(subset):
            total_sec, last_in = 0, None
            for _, row in subset.iterrows():
                if row['action'] == 'IN': last_in = row['timestamp']
                elif row['action'] == 'OUT' and last_in:
                    total_sec += (row['timestamp'] - last_in).total_seconds()
                    last_in = None
            return round(total_sec / 3600, 2)

        report.append({
            "Employee": user,
            "Week Hours": calc_hours(user_data[user_data['timestamp'] >= start_of_week]),
            "YTD Hours": calc_hours(user_data[user_data['timestamp'] >= start_of_year])
        })
    return pd.DataFrame(report)

# --- 4. INTERFACE ---
st.set_page_config(page_title="Walia Time Management", layout="wide")

if 'logged_in' not in st.session_state:
    st.session_state.update({'logged_in': False, 'user': None, 'role': None})

if not st.session_state['logged_in']:
    st.markdown("<h2 style='text-align: center;'>SYSTEM LOGIN</h2>", unsafe_allow_html=True)
    col1, col2, col3 = st.columns([1,1,1])
    with col2:
        pin = st.text_input("ENTER PIN", type="password")
        if st.button("LOGIN", use_container_width=True):
            c.execute('SELECT role, status, username FROM users WHERE password = ?', (pin,))
            res = c.fetchone()
            if res and (res[1] == 'approved' or res[0] == 'employer'):
                st.session_state.update({'logged_in': True, 'user': res[2], 'role': res[0]})
                st.rerun()
            else: st.error("Access Denied.")
        
        if st.button("REGISTER NEW STAFF", use_container_width=True):
            st.session_state['show_reg'] = True

    if st.session_state.get('show_reg'):
        with st.expander("Register New Account", expanded=True):
            nu = st.text_input("Full Name")
            np = st.text_input("Set Numeric PIN")
            photo = st.camera_input("Capture ID Photo")
            if st.button("Submit Registration"):
                c.execute("INSERT INTO users VALUES (?, ?, 'employee', 'pending')", (nu, np))
                with open(f"{STAFF_ID_DIR}/{nu}.jpg", "wb") as f: f.write(photo.getbuffer())
                conn.commit()
                st.success("Sent to Manager for approval.")

else:
    st.sidebar.button("Logout", on_click=lambda: st.session_state.update({'logged_in': False}))

    if st.session_state['role'] == 'employee':
        st.header(f"Employee Portal: {st.session_state['user']}")
        cam = st.camera_input("Verify Identity to Clock In/Out")
        if cam:
            c1, c2 = st.columns(2)
            ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            if c1.button("CLOCK IN"):
                c.execute("INSERT INTO attendance VALUES (?, ?, 'IN', 'WEB')", (st.session_state['user'], ts))
                conn.commit()
                st.success(f"In at {ts}")
            if c2.button("CLOCK OUT"):
                c.execute("INSERT INTO attendance VALUES (?, ?, 'OUT', 'WEB')", (st.session_state['user'], ts))
                conn.commit()
                st.info(f"Out at {ts}")

    elif st.session_state['role'] == 'employer':
        st.title("MANAGER MENU")
        t1, t2 = st.tabs(["Employee Management", "Payroll Reports"])
        with t1:
            staff = pd.read_sql_query("SELECT username, password, status FROM users WHERE role='employee'", conn)
            for _, row in staff.iterrows():
                ca, cb, cc = st.columns([1,2,2])
                img = f"{STAFF_ID_DIR}/{row['username']}.jpg"
                if os.path.exists(img): ca.image(img, width=100)
                cb.write(f"**{row['username']}** | PIN: {row['password']}")
                if row['status'] == 'pending':
                    if cc.button(f"Approve {row['username']}"):
                        c.execute("UPDATE users SET status='approved' WHERE username=?", (row['username'],))
                        conn.commit(); st.rerun()
                if cc.button(f"Remove {row['username']}"):
                    c.execute("DELETE FROM users WHERE username=?", (row['username'],))
                    conn.commit(); st.rerun()
        with t2:
            df = pd.read_sql_query("SELECT * FROM attendance", conn)
            if not df.empty:
                report = get_payroll_report(df)
                st.dataframe(report)
                output = io.BytesIO()
                with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                    report.to_excel(writer, index=False)
                st.download_button("Download Excel", output.getvalue(), "Payroll.xlsx")
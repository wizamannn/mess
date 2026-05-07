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
IS_CLOUD = os.path.exists("/mount")
if IS_CLOUD:
    STAFF_ID_DIR = "/tmp/staff_ids"
    DAILY_LOG_BASE = "/tmp/logs"
    DB_PATH = "/tmp/business.db"
else:
    STAFF_ID_DIR = "staff_ids"
    DAILY_LOG_BASE = "attendance_photos"
    DB_PATH = "business.db"

for folder in [STAFF_ID_DIR, DAILY_LOG_BASE]:
    if not os.path.exists(folder):
        try: os.makedirs(folder, exist_ok=True)
        except: pass

# --- 2. DATABASE LOGIC ---
conn = sqlite3.connect(DB_PATH, check_same_thread=False)
c = conn.cursor()
c.execute('''CREATE TABLE IF NOT EXISTS users (username TEXT PRIMARY KEY, password TEXT, role TEXT, status TEXT)''')
c.execute('''CREATE TABLE IF NOT EXISTS attendance (username TEXT, timestamp TEXT, action TEXT, photo_path TEXT)''')

c.execute("SELECT * FROM users WHERE username='admin'")
if not c.fetchone():
    c.execute("INSERT INTO users VALUES ('admin', 'admin123', 'employer', 'approved')")
    conn.commit()

# --- 3. BUSINESS & PDF LOGIC ---
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

def generate_pdf_report(df, week_start):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", 'B', 16)
    pdf.cell(200, 10, txt="WEEKLY PAYROLL SUMMARY", ln=True, align='C')
    pdf.set_font("Arial", size=10)
    pdf.cell(200, 10, txt=f"Report Date: {datetime.now().strftime('%Y-%m-%d')}", ln=True, align='C')
    pdf.cell(200, 10, txt=f"Week Starting: {week_start.strftime('%Y-%m-%d')}", ln=True, align='C')
    pdf.ln(10)
    
    # Header
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(60, 10, "Employee Name", 1)
    pdf.cell(60, 10, "Total Hours", 1)
    pdf.cell(60, 10, "Total Pay", 1)
    pdf.ln()
    
    # Data
    pdf.set_font("Arial", size=12)
    total_payroll = 0
    for _, row in df.iterrows():
        pdf.cell(60, 10, str(row['Employee']), 1)
        pdf.cell(60, 10, str(row['Hours']), 1)
        pdf.cell(60, 10, f"${row['Pay ($15/hr)']}", 1)
        pdf.ln()
        total_payroll += row['Pay ($15/hr)']
        
    pdf.ln(5)
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(120, 10, "GRAND TOTAL PAYROLL", 1)
    pdf.cell(60, 10, f"${round(total_payroll, 2)}", 1)
    
    return pdf.output(dest='S').encode('latin-1')

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
        
        st.write("---")
        if st.button("NEW STAFF SIGNUP", use_container_width=True):
            st.session_state['show_signup'] = True

    if st.session_state.get('show_signup'):
        with st.expander("Register New Account", expanded=True):
            nu = st.text_input("Full Name")
            np = st.text_input("Set Numeric PIN")
            reg_photo = st.camera_input("Capture ID Photo")
            if st.button("Submit Registration"):
                if nu and np and reg_photo:
                    try:
                        c.execute("INSERT INTO users VALUES (?, ?, 'employee', 'pending')", (nu, np))
                        with open(f"{STAFF_ID_DIR}/{nu}.jpg", "wb") as f: f.write(reg_photo.getbuffer())
                        conn.commit()
                        st.success("Sent to Manager for approval!")
                    except: st.error("User or PIN already exists.")
                if st.button("Back to Login"):
                    st.session_state['show_signup'] = False
                    st.rerun()

else:
    st.sidebar.button("EXIT SYSTEM", on_click=lambda: st.session_state.update({'logged_in': False}))

    if st.session_state['role'] == 'employee':
        st.header(f"Employee: {st.session_state['user']}")
        last_log = c.execute('''SELECT action FROM attendance WHERE username = ? 
                                ORDER BY timestamp DESC LIMIT 1''', 
                             (st.session_state['user'],)).fetchone()
        current_status = last_log[0] if last_log else 'OUT'
        cam = st.camera_input("Verify Face")
        if cam:
            ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            if current_status == 'OUT':
                if st.button("CLOCK IN", use_container_width=True, type="primary"):
                    c.execute("INSERT INTO attendance VALUES (?, ?, 'IN', 'WEB')", (st.session_state['user'], ts))
                    conn.commit()
                    st.success("Clocked In!")
                    st.rerun()
            else:
                if st.button("CLOCK OUT", use_container_width=True):
                    c.execute("INSERT INTO attendance VALUES (?, ?, 'OUT', 'WEB')", (st.session_state['user'], ts))
                    conn.commit()
                    st.info("Clocked Out!")
                    st.rerun()

    elif st.session_state['role'] == 'employer':
        st.title("MANAGER CONTROL")
        t1, t2, t3 = st.tabs(["Employees", "Logs", "Payroll Reports"])
        
        with t1:
            staff = pd.read_sql_query("SELECT username, password, status FROM users WHERE role='employee'", conn)
            for _, row in staff.iterrows():
                ca, cb, cc = st.columns([1,2,2])
                img_path = f"{STAFF_ID_DIR}/{row['username']}.jpg"
                if os.path.exists(img_path): ca.image(img_path, width=100)
                cb.write(f"**{row['username']}** | PIN: `{row['password']}`")
                if row['status'] == 'pending':
                    if cc.button(f"Approve {row['username']}"):
                        c.execute("UPDATE users SET status='approved' WHERE username=?", (row['username'],))
                        conn.commit(); st.rerun()
                if cc.button(f"Delete {row['username']}"):
                    c.execute("DELETE FROM users WHERE username=?", (row['username'],))
                    conn.commit(); st.rerun()

        with t2:
            st.subheader("Attendance Log History")
            logs = pd.read_sql_query("SELECT * FROM attendance ORDER BY timestamp DESC", conn)
            st.dataframe(logs, use_container_width=True)
        
        with t3:
            st.subheader("Weekly Financial Summary")
            df_all = pd.read_sql_query("SELECT * FROM attendance", conn)
            if not df_all.empty:
                stats, week_start = get_weekly_stats(df_all)
                st.write(f"### Pay Period Starting: {week_start.strftime('%B %d, %Y')}")
                st.dataframe(stats, use_container_width=True)
                
                col_ex, col_pdf = st.columns(2)
                
                # Excel Download
                excel_buf = io.BytesIO()
                with pd.ExcelWriter(excel_buf, engine='xlsxwriter') as writer:
                    stats.to_excel(writer, index=False)
                col_ex.download_button("📥 Download Excel Report", excel_buf.getvalue(), "Payroll_Summary.xlsx")
                
                # PDF Download
                pdf_data = generate_pdf_report(stats, week_start)
                col_pdf.download_button("📄 Download PDF Report", pdf_data, "Weekly_Payroll.pdf", "application/pdf")
            else:
                st.info("No data recorded for this week yet.")

import streamlit as st
import sqlite3
import pandas as pd
from datetime import datetime, timedelta
import os
import cv2
import numpy as np
import io
from fpdf import FPDF

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

# Default Admin
c.execute("SELECT * FROM users WHERE username='admin'")
if not c.fetchone():
    c.execute("INSERT INTO users VALUES ('admin', 'admin123', 'employer', 'approved')")
    conn.commit()

# --- 3. PAYROLL & REPORTING ENGINE ---
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

def generate_pdf(df, week_start):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", 'B', 16)
    pdf.cell(200, 10, txt="WEEKLY PAYROLL REPORT", ln=True, align='C')
    pdf.set_font("Arial", size=10)
    pdf.cell(200, 10, txt=f"Week Starting: {week_start.strftime('%Y-%m-%d')}", ln=True, align='C')
    pdf.ln(10)
    
    # Table Header
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(60, 10, "Employee", 1)
    pdf.cell(60, 10, "Total Hours", 1)
    pdf.cell(60, 10, "Total Pay", 1)
    pdf.ln()
    
    # Table Data
    pdf.set_font("Arial", size=12)
    for _, row in df.iterrows():
        pdf.cell(60, 10, str(row['Employee']), 1)
        pdf.cell(60, 10, str(row['Hours']), 1)
        pdf.cell(60, 10, f"${row['Pay ($15/hr)']}", 1)
        pdf.ln()
    
    return pdf.output(dest='S').encode('latin-1')

# --- 4. APP INTERFACE ---
st.set_page_config(page_title="Walia Payroll System", layout="wide")

if 'logged_in' not in st.session_state:
    st.session_state.update({'logged_in': False, 'user': None, 'role': None})

if not st.session_state['logged_in']:
    st.markdown("<h2 style='text-align: center;'>ENTER PIN</h2>", unsafe_allow_html=True)
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
        cam = st.camera_input("Verification")
        if cam:
            c1, c2 = st.columns(2)
            ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            if c1.button("CLOCK IN", use_container_width=True):
                c.execute("INSERT INTO attendance VALUES (?, ?, 'IN', 'WEB')", (st.session_state['user'], ts))
                conn.commit(); st.success("Clocked In")
            if c2.button("CLOCK OUT", use_container_width=True):
                c.execute("INSERT INTO attendance VALUES (?, ?, 'OUT', 'WEB')", (st.session_state['user'], ts))
                conn.commit(); st.info("Clocked Out")

    elif st.session_state['role'] == 'employer':
        st.title("MANAGER MENU")
        t1, t2, t3 = st.tabs(["Employee List", "Attendance Logs", "Payroll Reports"])
        
        with t2:
            st.subheader("Manual Log Correction")
            with st.expander("Add Missing Punch"):
                e_name = st.selectbox("Select Employee", [r[0] for r in c.execute("SELECT username FROM users WHERE role='employee'").fetchall()])
                e_date = st.date_input("Date")
                e_time = st.time_input("Time")
                e_action = st.selectbox("Action", ["IN", "OUT"])
                if st.button("Add Manual Entry"):
                    dt = f"{e_date} {e_time}"
                    c.execute("INSERT INTO attendance VALUES (?, ?, ?, 'MANUAL')", (e_name, dt, e_action))
                    conn.commit(); st.rerun()
            
            logs = pd.read_sql_query("SELECT * FROM attendance ORDER BY timestamp DESC", conn)
            st.dataframe(logs, use_container_width=True)

        with t3:
            st.subheader("Weekly Payroll Generation")
            df_all = pd.read_sql_query("SELECT * FROM attendance", conn)
            if not df_all.empty:
                stats, week_start = get_weekly_stats(df_all)
                st.write(f"### Pay Period: {week_start.strftime('%B %d')} to Today")
                st.dataframe(stats, use_container_width=True)
                
                c_pdf, c_xlsx = st.columns(2)
                
                # Excel Export
                excel_buf = io.BytesIO()
                with pd.ExcelWriter(excel_buf, engine='xlsxwriter') as writer:
                    stats.to_excel(writer, index=False, sheet_name='Payroll')
                c_xlsx.download_button("📥 Download Excel (Detail)", excel_buf.getvalue(), "Weekly_Payroll.xlsx")
                
                # PDF Export
                pdf_bytes = generate_pdf(stats, week_start)
                c_pdf.download_button("📄 Download PDF (Official)", pdf_bytes, "Weekly_Payroll.pdf", "application/pdf")
            else:
                st.info("No logs found for this week.")

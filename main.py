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
# We use /tmp/ for folders on Streamlit Cloud to avoid "Permission Denied" errors
if os.path.exists("/mount/src/mess"):
    # This is the path for Streamlit Cloud
    STAFF_ID_DIR = "/tmp/permanent_staff_ids"
    DAILY_LOG_BASE = "/tmp/attendance_photos"
    DB_PATH = "/tmp/company_data.db"
else:
    # This is the path for your local computer
    STAFF_ID_DIR = "permanent_staff_ids"
    DAILY_LOG_BASE = "attendance_photos"
    DB_PATH = "company_data.db"

for folder in [STAFF_ID_DIR, DAILY_LOG_BASE]:
    if not os.path.exists(folder):
        os.makedirs(folder, exist_ok=True)

# --- 2. DATABASE LOGIC (Updated to use DB_PATH) ---
conn = sqlite3.connect(DB_PATH, check_same_thread=False)
c = conn.cursor()

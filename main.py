# --- EMPLOYEE VIEW (Smart Toggle Logic) ---
    if st.session_state['role'] == 'employee':
        st.header(f"Employee: {st.session_state['user']}")
        
        # Check database for the last action of this user
        last_log = c.execute('''SELECT action FROM attendance 
                                WHERE username = ? 
                                ORDER BY timestamp DESC LIMIT 1''', 
                             (st.session_state['user'],)).fetchone()
        
        # Determine status (Default to 'OUT' if no logs exist)
        current_status = last_log[0] if last_log else 'OUT'
        
        cam = st.camera_input("Verify Face to Proceed")
        if cam:
            ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            # Logic: If last action was OUT, they can only CLOCK IN
            if current_status == 'OUT':
                st.info("Status: Currently Clocked Out")
                if st.button("CLOCK IN", use_container_width=True, type="primary"):
                    c.execute("INSERT INTO attendance VALUES (?, ?, 'IN', 'WEB')", (st.session_state['user'], ts))
                    conn.commit()
                    st.success(f"Success! Clocked In at {ts}")
                    st.rerun() # Refresh to update the button
            
            # Logic: If last action was IN, they can only CLOCK OUT
            elif current_status == 'IN':
                st.warning("Status: Currently Clocked In")
                if st.button("CLOCK OUT", use_container_width=True):
                    c.execute("INSERT INTO attendance VALUES (?, ?, 'OUT', 'WEB')", (st.session_state['user'], ts))
                    conn.commit()
                    st.info(f"Success! Clocked Out at {ts}")
                    st.rerun() # Refresh to update the button

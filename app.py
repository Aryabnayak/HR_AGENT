import streamlit as st
import requests
import uuid
import pandas as pd
import os


try:
    # 1. Map Streamlit Secrets to System Environment Variables
    for key, value in st.secrets.items():
        if key not in ["CREDENTIALS_JSON", "MCP_SERVERS_JSON"]:
            os.environ[key] = str(value)

    # 2. Recreate the physical JSON files required by the agents
    if "CREDENTIALS_JSON" in st.secrets:
        with open("credentials.json", "w", encoding="utf-8") as f:
            f.write(st.secrets["CREDENTIALS_JSON"])

    if "MCP_SERVERS_JSON" in st.secrets:
        with open("mcp_servers.json", "w", encoding="utf-8") as f:
            f.write(st.secrets["MCP_SERVERS_JSON"])
except Exception as e:
    # If running locally without st.secrets, it safely ignores this block
    print(f"Skipping cloud secrets injection: {e}")


st.set_page_config(page_title="Agentic Talent Engine", layout="wide")

if "session_id" not in st.session_state:
    st.session_state["session_id"] = str(uuid.uuid4())

st.title("🤖 Autonomous Talent Acquisition Engine")
st.markdown("Powered by Autogen, Llama-3, LangChain, and MCP Tools.")

# --- NEW: We now have 4 tabs! ---
tab1, tab2, tab3, tab4 = st.tabs(["Agent Control Center", "ATS Database", "🗓️ Schedule Interviews", "⚖️ Interview Decisions"])

with tab1:
    st.header("Initiate Recruitment Protocol")
    job_desc = st.text_area("Enter Job Description & Search Parameters", 
                            "Looking for a Senior Python Developer with LangChain experience...")
    
    if st.button("Deploy Agents"):
        with st.spinner("Agents are hunting, negotiating, and updating systems. This may take a minute..."):
            try:
                response = requests.post("http://localhost:8000/api/v1/trigger_recruitment", 
                                         json={"session_id": st.session_state["session_id"], "job_description": job_desc})
                if response.status_code == 200:
                    st.success("Workflow Complete!")
                    with st.expander("View Multi-Agent Conversation Log"):
                        st.text(response.json()["chat_log"])
                else:
                    st.error(f"Backend Error: {response.text}")
            except requests.exceptions.ConnectionError:
                st.error("Uvicorn backend is not running.")

with tab2:
    st.header("Candidate Pipeline")
    if st.button("Refresh Database"):
        try:
            res = requests.get("http://localhost:8000/api/v1/candidates")
            if res.status_code == 200:
                data = res.json()
                if data:
                    df = pd.DataFrame(data)
                    def highlight_status(val):
                        color = '#4CAF50' if val == 'Selected' else '#F44336' if val == 'Rejected' else '#FFC107'
                        return f'background-color: {color}'
                    st.dataframe(df.style.applymap(highlight_status, subset=['status']))
                else:
                    st.info("No candidates processed yet.")
        except:
            st.error("Could not connect to Database API.")

# --- NEW: MANUAL SCHEDULING TAB ---
with tab3:
    st.header("🗓️ Manual Calendar Scheduling")
    st.markdown("Select a candidate who has replied 'Yes' to the AI's email and pick a time slot.")
    
    try:
        res = requests.get("http://localhost:8000/api/v1/candidates")
        if res.status_code == 200 and res.json():
            candidates = res.json()
            # Filter for active candidates
            active_cands = [c for c in candidates if c['status'] in ['Pending', 'Interviewing']]
            
            if not active_cands:
                st.info("No candidates available for scheduling.")
            else:
                c_names = [f"{c['name']} - {c['role']}" for c in active_cands]
                selected_c_str = st.selectbox("Select Candidate", c_names)
                
                selected_c = next(c for c in active_cands if f"{c['name']} - {c['role']}" == selected_c_str)
                
                # Auto-fill email format removed, replaced with empty string and placeholder
                c_email = st.text_input("Candidate Email for Invite", value="", placeholder="Paste the real email from the AI log here...")
                
                # Natural language date input (e.g., "Next Tuesday at 3 PM")
                time_slot = st.text_input("Interview Date & Time", placeholder="e.g., Tomorrow at 2 PM, or 2026-06-15 14:00")
                
                if st.button("Generate Google Calendar Invite"):
                    if not time_slot:
                        st.warning("Please enter a time slot.")
                    else:
                        with st.spinner("Talking to Google Calendar API..."):
                            payload = {"candidate_email": c_email, "time_slot": time_slot}
                            sched_res = requests.post("http://localhost:8000/api/v1/schedule_manual", json=payload)
                            
                            if sched_res.status_code == 200:
                                st.success("Interview Scheduled Successfully!")
                                st.info(sched_res.json()["result"])
                            else:
                                st.error(f"Error: {sched_res.text}")
        else:
            st.info("No candidates in the database.")
    except Exception as e:
        st.error("Backend connection failed.")

with tab4:
    st.header("⚖️ Submit Interview Decisions")
    try:
        res = requests.get("http://localhost:8000/api/v1/candidates")
        if res.status_code == 200 and res.json():
            candidates = res.json()
            pending_candidates = [c for c in candidates if c['status'] in ['Pending', 'Interviewing']]
            
            if not pending_candidates:
                st.info("No candidates are currently awaiting an interview decision.")
            else:
                candidate_names = [f"{c['name']} - {c['role']}" for c in pending_candidates]
                selected_candidate_str = st.selectbox("Select Candidate to Evaluate", candidate_names, key="eval_box")
                selected_c = next(c for c in pending_candidates if f"{c['name']} - {c['role']}" == selected_candidate_str)
                
                c_name = st.text_input("Candidate Name", value=selected_c['name'], disabled=True)
                # Auto-fill email format removed, replaced with empty string and placeholder
                c_email = st.text_input("Candidate Email", value="", placeholder="Paste the real email from the AI log here...", key="eval_email") 
                c_role = st.text_input("Target Role", value=selected_c['role'], disabled=True)
                
                decision = st.radio("Final Decision", ["Selected", "Rejected"])
                
                if st.button("Submit Decision & Trigger Agents"):
                    with st.spinner(f"Triggering workflow for {decision} candidate..."):
                        payload = {
                            "session_id": st.session_state["session_id"],
                            "candidate_name": c_name, "candidate_email": c_email,
                            "target_role": c_role, "decision": decision
                        }
                        response = requests.post("http://localhost:8000/api/v1/interview_result", json=payload)
                        if response.status_code == 200:
                            st.success(f"Agents successfully executed the {decision} protocol!")
                            with st.expander("View Execution Log"):
                                st.text(response.json()["chat_log"])
                        else:
                            st.error(f"Error triggering agents: {response.text}")
    except:
        st.error("Failed to connect to backend.")

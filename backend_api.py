from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import uvicorn
from database import SessionLocal, Candidate

app = FastAPI(title="Agentic ATS Backend")

class JobRequest(BaseModel):
    session_id: str
    job_description: str

class DecisionRequest(BaseModel):
    session_id: str
    candidate_name: str
    candidate_email: str
    target_role: str
    decision: str

# --- NEW: Manual Scheduling Model ---
class ScheduleRequest(BaseModel):
    candidate_email: str
    time_slot: str

@app.post("/api/v1/trigger_recruitment")
async def trigger_recruitment(req: JobRequest):
    try:
        from agent_orchestator import run_recruitment_workflow
        chat_log = run_recruitment_workflow(req.job_description, req.session_id)
        return {"status": "success", "chat_log": chat_log}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/v1/interview_result")
async def submit_interview_result(req: DecisionRequest):
    try:
        from agent_orchestator import process_interview_result
        chat_log = process_interview_result(
            name=req.candidate_name,
            email=req.candidate_email,
            role=req.target_role,
            decision=req.decision,
            session_id=req.session_id
        )
        return {"status": "success", "chat_log": chat_log}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# --- NEW: Manual Scheduling Endpoint ---
@app.post("/api/v1/schedule_manual")
async def schedule_manual(req: ScheduleRequest):
    try:
        # We import the tool and call its raw python function directly!
        from mcp_tools_bridge import mcp_schedule_interview
        result = mcp_schedule_interview.func(candidate_email=req.candidate_email, time_slot=req.time_slot)
        return {"status": "success", "result": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/v1/candidates")
async def get_candidates():
    db = SessionLocal()
    try:
        candidates = db.query(Candidate).all()
        return candidates
    finally:
        db.close()

if __name__ == "__main__":
    uvicorn.run("backend_api:app", host="0.0.0.0", port=8000, reload=False)
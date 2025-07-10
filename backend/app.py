#
# backend/app.py - The Correct FastAPI Server Code
#
import os
import uuid
import tempfile
from fastapi import FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Dict

from agent_logic import app_graph, GraphState, deployment_planning_tool, execution_tool
from langchain_core.messages import HumanMessage, AIMessage, BaseMessage

# --- FastAPI App Setup ---
app = FastAPI()

# --- CORS Configuration ---
# Allows the frontend (running on a different port) to communicate with this backend
origins = [
    "http://localhost",
    "http://localhost:8000",
    "http://127.0.0.1",
    "http://127.0.0.1:8000",
    # Add this line to allow opening the file directly in the browser
    "null",
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- State Management ---
# In-memory dictionary to store session states.
# For production, you'd replace this with Redis, a database, etc.
SESSIONS: Dict[str, GraphState] = {}

# Create and mount the directory for serving generated files like diagrams
# The directory is relative to where the script is run
os.makedirs("generated_files", exist_ok=True)
app.mount("/generated_files", StaticFiles(directory="generated_files"), name="generated_files")

# --- Pydantic Models for API Requests/Responses ---
class ChatRequest(BaseModel):
    session_id: str | None = None
    message: str

class PlanRequest(BaseModel):
    session_id: str

class ApplyRequest(BaseModel):
    session_id: str

# Helper to serialize BaseMessage objects for JSON responses
def serialize_history(history: List[BaseMessage]) -> List[Dict]:
    serialized = []
    for msg in history:
        role = "user" if isinstance(msg, HumanMessage) else "assistant"
        serialized.append({"role": role, "content": msg.content})
    return serialized

# --- API Endpoints ---
@app.post("/api/chat")
async def chat(request: ChatRequest):
    session_id = request.session_id or str(uuid.uuid4())

    if session_id not in SESSIONS:
        # Create a new session if it doesn't exist
        # Make sure the temp dir is created inside the mounted directory
        temp_dir = tempfile.mkdtemp(dir="generated_files")
        SESSIONS[session_id] = GraphState(
            work_dir=temp_dir,
            initial_request="",
            conversation_history=[],
            iac_code="",
            iac_diagram_path="",
            plan_output="",
            apply_output="",
            clarification_questions=[],
            error_message=""
        )

    # Get the current state for the session
    current_state = SESSIONS[session_id]
    
    # Append the user's message to the conversation history
    current_state["conversation_history"].append(HumanMessage(content=request.message))

    # Invoke the graph
    try:
        # Make sure to pass the state correctly
        result_state = app_graph.invoke(current_state, config={"recursion_limit": 10})
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Agent graph execution failed: {str(e)}")

    # Update the session with the new state
    SESSIONS[session_id].update(result_state)

    # Add the assistant's response to the history for the next turn
    if result_state.get("error_message"):
        response_text = result_state["error_message"]
    elif result_state.get("iac_code"):
         response_text = "I have updated the architecture based on your request. You can see the new code and diagram. What would you like to do next?"
    else:
        response_text = "I'm not sure how to proceed. Could you please clarify?"
        
    SESSIONS[session_id]["conversation_history"].append(AIMessage(content=response_text))

    # Return the complete, updated state to the frontend
    response_data = SESSIONS[session_id].copy()
    response_data["session_id"] = session_id
    response_data["conversation_history"] = serialize_history(response_data["conversation_history"])
    
    return response_data

@app.post("/api/plan")
async def plan(request: PlanRequest):
    session_id = request.session_id
    if session_id not in SESSIONS:
        raise HTTPException(status_code=404, detail="Session not found")

    current_state = SESSIONS[session_id]
    plan_result = deployment_planning_tool(current_state)
    current_state.update(plan_result)
    current_state["apply_output"] = "" # Clear previous apply output
    SESSIONS[session_id] = current_state

    response_data = SESSIONS[session_id].copy()
    response_data["session_id"] = session_id
    response_data["conversation_history"] = serialize_history(response_data["conversation_history"])
    return response_data

@app.post("/api/apply")
async def apply(request: ApplyRequest):
    session_id = request.session_id
    if session_id not in SESSIONS:
        raise HTTPException(status_code=404, detail="Session not found")
        
    current_state = SESSIONS[session_id]
    apply_result = execution_tool(current_state)
    current_state.update(apply_result)
    current_state["plan_output"] = "" # Clear plan output after apply
    SESSIONS[session_id] = current_state

    response_data = SESSIONS[session_id].copy()
    response_data["session_id"] = session_id
    response_data["conversation_history"] = serialize_history(response_data["conversation_history"])
    return response_data

# --- Serve Frontend ---
# This serves the static files from the 'frontend' directory, which is one level up.
app.mount("/", StaticFiles(directory="../frontend", html=True), name="static")

@app.get("/{full_path:path}")
async def catch_all(request: Request, full_path: str):
    # This catch-all is to ensure that refreshing a page doesn't 404
    return app.send_static_file("index.html")
import os
import uuid
import tempfile
import logging
import json
from datetime import datetime

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import List, Dict, Optional
from dotenv import load_dotenv, set_key

from agent_logic import app_graph, GraphState, deployment_planning_tool, execution_tool
from langchain_core.messages import HumanMessage, AIMessage, BaseMessage

# Load environment variables at startup
load_dotenv()

app = FastAPI()
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- Middleware for CORS ---
origins = [
    "http://localhost", "http://localhost:8000",
    "http://127.0.0.1", "http://127.0.0.1:8000",
    "null", 
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins, allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)

# --- Directory setup ---
os.makedirs("generated_files", exist_ok=True)
os.makedirs("sessions", exist_ok=True)
app.mount("/generated_files", StaticFiles(directory="generated_files"), name="generated_files")

# --- Pydantic Models ---
class ApiRequest(BaseModel):
    session_id: str | None = None

class ChatRequest(ApiRequest):
    message: str
    
class ConfigRequest(BaseModel):
    google_api_key: Optional[str] = None
    aws_access_key_id: Optional[str] = None
    aws_secret_access_key: Optional[str] = None
    aws_default_region: Optional[str] = None

# --- Session Serialization/Deserialization ---
def serialize_history(history: List[BaseMessage]) -> List[Dict]:
    serializable = []
    for msg in history:
        role = "user" if isinstance(msg, HumanMessage) else "assistant"
        serializable.append({"role": role, "content": msg.content})
    return serializable

def deserialize_history(history_data: List[Dict]) -> List[BaseMessage]:
    messages = []
    for msg in history_data:
        if msg['role'] == 'user':
            messages.append(HumanMessage(content=msg['content']))
        else:
            messages.append(AIMessage(content=msg['content']))
    return messages

# --- Session Management ---
SESSIONS: Dict[str, GraphState] = {} # This will now act as a cache

def save_session_state(session_id: str, state: GraphState):
    """Saves a session's state to a JSON file."""
    session_file = os.path.join("sessions", f"{session_id}.json")
    
    # Create a serializable copy of the state
    serializable_state = state.copy()
    serializable_state["conversation_history"] = serialize_history(state["conversation_history"])
    
    with open(session_file, "w") as f:
        json.dump(serializable_state, f, indent=2)

def get_session_state(session_id: str | None) -> (str, GraphState):
    """Retrieves state from file or creates a new session."""
    sid = session_id or str(uuid.uuid4())
    session_file = os.path.join("sessions", f"{sid}.json")

    if sid in SESSIONS:
        return sid, SESSIONS[sid]

    if os.path.exists(session_file):
        logging.info(f"Loading existing session {sid} from disk.")
        with open(session_file, "r") as f:
            state_data = json.load(f)
        state_data["conversation_history"] = deserialize_history(state_data["conversation_history"])
        SESSIONS[sid] = state_data
        return sid, SESSIONS[sid]

    logging.info(f"Creating new session: {sid}")
    temp_dir = tempfile.mkdtemp(dir="generated_files")
    new_state = GraphState(
        work_dir=temp_dir, initial_request="", conversation_history=[],
        intent="", chat_response="", iac_code="", iac_diagram_path="",
        plan_output="", apply_output="", clarification_questions=[], error_message=""
    )
    SESSIONS[sid] = new_state
    save_session_state(sid, new_state)
    return sid, new_state

# --- API Endpoints ---
@app.post("/api/chat")
async def chat(request: ChatRequest):
    session_id, current_state = get_session_state(request.session_id)
    
    # Handle initial load for an existing session
    if request.message == "__initial_load__" and current_state["conversation_history"]:
        pass # Just load the state and return it
    else:
        code_before_run = current_state.get("iac_code", "")
        current_state["conversation_history"].append(HumanMessage(content=request.message))
        
        try:
            result_state = app_graph.invoke(current_state, config={"recursion_limit": 10})
        except Exception as e:
            logging.error(f"Graph execution error for session {session_id}: {e}")
            raise HTTPException(status_code=500, detail=f"Agent graph execution failed: {str(e)}")

        response_text = ""
        if result_state.get("chat_response"):
            response_text = result_state["chat_response"]
            result_state["chat_response"] = "" 
        elif result_state.get("clarification_questions"):
            questions = result_state["clarification_questions"]
            response_text = "I have a few questions:\n- " + "\n- ".join(questions)
        elif result_state.get("error_message"):
            response_text = result_state["error_message"]
        elif result_state.get("iac_code") and result_state["iac_code"] != code_before_run:
            response_text = "I have updated the architecture. Review the code and diagram, and let me know what to do next."
        
        SESSIONS[session_id].update(result_state)
        if response_text:
            SESSIONS[session_id]["conversation_history"].append(AIMessage(content=response_text))

    save_session_state(session_id, SESSIONS[session_id])
    
    response_data = SESSIONS[session_id].copy()
    response_data["session_id"] = session_id
    response_data["conversation_history"] = serialize_history(response_data["conversation_history"])
    return response_data

@app.post("/api/plan")
async def plan(request: ApiRequest):
    session_id, current_state = get_session_state(request.session_id)
    if not current_state.get("iac_code"):
        raise HTTPException(status_code=400, detail="No IaC code available to plan.")
    
    plan_result = deployment_planning_tool(current_state)
    current_state.update(plan_result)
    current_state["apply_output"] = "" 
    save_session_state(session_id, current_state)
    
    response_data = current_state.copy()
    response_data["session_id"] = session_id
    response_data["conversation_history"] = serialize_history(response_data["conversation_history"])
    return response_data

@app.post("/api/apply")
async def apply(request: ApiRequest):
    session_id, current_state = get_session_state(request.session_id)
    if not current_state.get("plan_output"):
         raise HTTPException(status_code=400, detail="A plan must be generated before applying.")
    apply_result = execution_tool(current_state)
    current_state.update(apply_result)
    current_state["plan_output"] = "" 
    save_session_state(session_id, current_state)
    
    response_data = current_state.copy()
    response_data["session_id"] = session_id
    response_data["conversation_history"] = serialize_history(response_data["conversation_history"])
    return response_data

# --- Configuration & Session List Endpoints ---
@app.post("/api/save_config")
async def save_config(request: ConfigRequest):
    try:
        dotenv_path = os.path.join(os.path.dirname(__file__), '.env')
        if not os.path.exists(dotenv_path):
            open(dotenv_path, 'a').close() # Create .env if it doesn't exist
            
        for key, value in request.model_dump().items():
            if value: # Only set keys that have a value
                set_key(dotenv_path, key.upper(), value)
        
        load_dotenv(override=True) # Reload env vars for the current process
        return {"message": "Configuration saved successfully!"}
    except Exception as e:
        logging.error(f"Failed to save .env file: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/get_config")
async def get_config():
    load_dotenv()
    return {
        "google_api_key_set": bool(os.getenv("GOOGLE_API_KEY")),
        "aws_access_key_id_set": bool(os.getenv("AWS_ACCESS_KEY_ID")),
        "aws_secret_access_key_set": bool(os.getenv("AWS_SECRET_ACCESS_KEY")),
        "aws_default_region": os.getenv("AWS_DEFAULT_REGION", "")
    }

@app.get("/api/sessions")
async def list_sessions():
    sessions_dir = "sessions"
    session_files = [f for f in os.listdir(sessions_dir) if f.endswith('.json')]
    sessions_data = []
    for filename in session_files:
        session_id = filename.replace('.json', '')
        filepath = os.path.join(sessions_dir, filename)
        try:
            with open(filepath, 'r') as f:
                data = json.load(f)
                history = data.get("conversation_history", [])
                first_message = history[0]['content'] if history else "Empty Chat"
                title = (first_message[:50] + '...') if len(first_message) > 50 else first_message
                
                sessions_data.append({
                    "id": session_id,
                    "title": title,
                    "last_modified": os.path.getmtime(filepath)
                })
        except Exception as e:
            logging.error(f"Could not read session file {filename}: {e}")
            continue
    # Sort by most recently modified
    sessions_data.sort(key=lambda x: x['last_modified'], reverse=True)
    return sessions_data

# --- Static File Serving ---
@app.get("/{full_path:path}")
async def serve_frontend(request: Request, full_path: str):
    base_dir = os.path.join(os.path.dirname(__file__), "../frontend")
    
    # If no path, serve start.html as the default
    if not full_path:
        full_path = "start.html"
        
    file_path = os.path.join(base_dir, full_path)
    if os.path.exists(file_path):
        return FileResponse(file_path)

    # Fallback to serving start.html for SPA-like behavior on refresh
    start_path = os.path.join(base_dir, "start.html")
    if os.path.exists(start_path):
        return FileResponse(start_path)

    raise HTTPException(status_code=404, detail="Not Found")
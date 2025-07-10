import os
import uuid
import tempfile
import logging
from fastapi.staticfiles import StaticFiles
from fastapi import FastAPI, HTTPException, Request 

from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Dict

from agent_logic import app_graph, GraphState, deployment_planning_tool, execution_tool
from langchain_core.messages import HumanMessage, AIMessage, BaseMessage

app = FastAPI()
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

origins = [
    "http://localhost",
    "http://localhost:8000",
    "http://127.0.0.1",
    "http://127.0.0.1:8000",
    "null", 
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


SESSIONS: Dict[str, GraphState] = {}

os.makedirs("generated_files", exist_ok=True)
app.mount("/generated_files", StaticFiles(directory="generated_files"), name="generated_files")

class ApiRequest(BaseModel):
    """Base model for requests that only need a session ID."""
    session_id: str | None = None

class ChatRequest(ApiRequest):
    """Model for chat requests, which also include a message."""
    message: str

def serialize_history(history: List[BaseMessage]) -> List[Dict]:
    """Converts LangChain message objects to a JSON-serializable format for the frontend."""
    return [{"role": "user" if isinstance(msg, HumanMessage) else "assistant", "content": msg.content} for msg in history]

def get_session_state(session_id: str | None) -> (str, GraphState):
    """
    Retrieves the state for a given session ID or creates a new one if it doesn't exist.
    This encapsulates session creation logic.
    """
    sid = session_id or str(uuid.uuid4())
    if sid not in SESSIONS:
        logging.info(f"Creating new session: {sid}")
        temp_dir = tempfile.mkdtemp(dir="generated_files")
        SESSIONS[sid] = GraphState(
            work_dir=temp_dir,
            initial_request="",
            conversation_history=[],
            intent="",
            chat_response="",
            iac_code="",
            iac_diagram_path="",
            plan_output="",
            apply_output="",
            clarification_questions=[],
            error_message=""
        )
    return sid, SESSIONS[sid]

# --- API Endpoints ---
@app.post("/api/chat")
async def chat(request: ChatRequest):
    """
    The main chat endpoint. It now intelligently handles different agent outputs.
    """
    session_id, current_state = get_session_state(request.session_id)
    
    code_before_run = current_state.get("iac_code", "")
    
    current_state["conversation_history"].append(HumanMessage(content=request.message))
    
    try:
        result_state = app_graph.invoke(current_state, config={"recursion_limit": 10})
    except Exception as e:
        logging.error(f"Graph execution error for session {session_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Agent graph execution failed: {str(e)}")


    response_text = ""
    if result_state.get("chat_response"):
        logging.info(f"Session {session_id}: Handling general chat response.")
        response_text = result_state["chat_response"]
        result_state["chat_response"] = "" 
    elif result_state.get("clarification_questions"):
        logging.info(f"Session {session_id}: Handling clarification questions.")
        questions = result_state["clarification_questions"]
        response_text = "I have a few questions to ensure I build this correctly:\n- " + "\n- ".join(questions)

    elif result_state.get("error_message"):
        logging.error(f"Session {session_id}: Handling error message.")
        response_text = result_state["error_message"]

    elif result_state.get("iac_code") and result_state["iac_code"] != code_before_run:
        logging.info(f"Session {session_id}: Handling successful code generation.")
        response_text = "I have updated the architecture based on your request. You can see the new code and diagram. What would you like to do next?"
    
    SESSIONS[session_id].update(result_state)
    
    if response_text:
        SESSIONS[session_id]["conversation_history"].append(AIMessage(content=response_text))

    response_data = SESSIONS[session_id].copy()
    response_data["session_id"] = session_id
    response_data["conversation_history"] = serialize_history(response_data["conversation_history"])
    
    return response_data

@app.post("/api/plan")
async def plan(request: ApiRequest):
    """Endpoint to run `terraform plan`."""
    session_id, current_state = get_session_state(request.session_id)
    if not current_state.get("iac_code"):
        raise HTTPException(status_code=400, detail="No IaC code available to plan.")
    
    plan_result = deployment_planning_tool(current_state)
    current_state.update(plan_result)
    current_state["apply_output"] = "" 
    
    response_data = current_state.copy()
    response_data["session_id"] = session_id
    response_data["conversation_history"] = serialize_history(response_data["conversation_history"])
    return response_data

@app.post("/api/apply")
async def apply(request: ApiRequest):
    """Endpoint to run `terraform apply`."""
    session_id, current_state = get_session_state(request.session_id)
    if not current_state.get("plan_output"):
         raise HTTPException(status_code=400, detail="A plan must be generated before applying.")

    apply_result = execution_tool(current_state)
    current_state.update(apply_result)
    current_state["plan_output"] = "" 
    
    response_data = current_state.copy()
    response_data["session_id"] = session_id
    response_data["conversation_history"] = serialize_history(response_data["conversation_history"])
    return response_data


app.mount("/", StaticFiles(directory="../frontend", html=True), name="static")

@app.get("/{full_path:path}")
async def catch_all_for_spa(request: Request, full_path: str):
    """
    Catch-all route to serve index.html for Single Page Applications (SPAs).
    This ensures that refreshing the page doesn't result in a 404 error.
    """
  
    if full_path.startswith("docs") or full_path.startswith("redoc"):
        raise HTTPException(status_code=404, detail="Not found")
    
    index_path = os.path.join("../frontend", "index.html")
    if os.path.exists(index_path):
        from fastapi.responses import FileResponse
        return FileResponse(index_path)
    
    raise HTTPException(status_code=404, detail="index.html not found")

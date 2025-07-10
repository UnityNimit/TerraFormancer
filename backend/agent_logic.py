import os
import subprocess
import json
import io
from typing import TypedDict, List
from langgraph.graph import StateGraph, END
from langchain_core.messages import BaseMessage, HumanMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from dotenv import load_dotenv
import hcl2
import logging

# --- Diagramming Imports ---
from diagrams import Diagram, Cluster
from diagrams.aws.compute import EC2, EC2AutoScaling, Lambda
from diagrams.aws.database import RDS
from diagrams.aws.network import ELB, VPC
from diagrams.aws.storage import S3

# --- Setup & Configuration ---
load_dotenv()
logging.basicConfig(level=logging.INFO)

# --- 1. AGENT STATE ---
class GraphState(TypedDict):
    work_dir: str
    initial_request: str
    conversation_history: List[BaseMessage]
    iac_code: str
    iac_diagram_path: str
    plan_output: str
    apply_output: str
    clarification_questions: List[str]
    error_message: str

# --- 2. LLM & AGENT NODES ---
try:
    llm = ChatGoogleGenerativeAI(model="gemini-1.5-flash", temperature=0.1)
except Exception as e:
    logging.error(f"Fatal: Error initializing LLM. Please check your GOOGLE_API_KEY. Details: {e}")
    # In a real app, this might terminate or enter a safe mode.
    # For this example, we'll let it raise the exception.
    raise

def iac_generation_agent(state: GraphState):
    logging.info("Executing iac_generation_agent...")
    aws_region = os.getenv("AWS_DEFAULT_REGION", "us-east-1")
    conversation_for_prompt = "\n".join([f"{msg.type}: {msg.content}" for msg in state['conversation_history']])
    existing_code = state.get("iac_code", "")

    if existing_code and "Error" not in existing_code:
        clean_existing_code = existing_code.replace("--- main.tf ---", "").strip()
        prompt = f"""
        You are an expert DevOps engineer who flawlessly modifies existing Terraform HCL code. Your task is to take an existing `main.tf` file and a user's request, and return a NEW, COMPLETE, and VALID `main.tf` file that incorporates the user's changes.
        **CRITICAL RULES:**
        1.  You MUST return the **entire, complete, and updated `main.tf` file**. Do not return snippets or explanations.
        2.  If adding a new resource that another resource depends on, you must add the new resource AND update the existing resource to reference it.
        3.  Resource names (e.g., `aws_instance.web_server`) must remain consistent unless the user asks to change them.
        ---
        **YOUR CURRENT TASK**
        **Full Conversation History:**
        {conversation_for_prompt}

        **Existing `main.tf` to modify:**
        ```hcl
        {clean_existing_code}
        ```
        Now, based on the last user message, return ONLY the full, updated, and raw HCL code for the new `main.tf` file.
        """
    else:
        prompt = f"""
        You are an expert DevOps engineer who writes lean, correct, and minimal Terraform HCL for AWS.
        Your task is to write a complete `main.tf` file from scratch that fulfills the user's request.
        **CRITICAL INSTRUCTIONS:**
        1.  **BE PRECISE:** Fulfill the user's request *exactly* as stated.
        2.  **NO EXTRAS:** Do **not** add extra resources (like logging buckets, complex IAM roles, etc.) unless they are *explicitly* requested in the prompt.
        3.  **INCLUDE PROVIDER:** The AWS provider block MUST include the region. Use `{aws_region}`.
        4.  **HCL ONLY:** Return ONLY the raw HCL code, without any markdown fences or explanations.
        **Full Conversation History:**
        {conversation_for_prompt}
        Write the Terraform code now.
        """
    
    response = llm.invoke(prompt)
    hcl_code = response.content.strip().replace("```hcl", "").replace("```", "").strip()

    # --- Validation ---
    try:
        with io.StringIO(hcl_code) as f:
            hcl2.load(f)
    except Exception as e:
        error_msg = f"**Validation Error:** Agent produced invalid HCL. Details: {e}\n\n---\n{hcl_code}"
        logging.error(error_msg)
        return {"iac_code": "", "error_message": error_msg}

    if "provider" not in hcl_code and "terraform {" not in hcl_code:
        error_msg = f"Error: LLM returned invalid HCL (missing provider).\n---\n{hcl_code}"
        logging.error(error_msg)
        return {"iac_code": "", "error_message": error_msg}
    
    iac_dir = state["work_dir"]
    with open(os.path.join(iac_dir, "main.tf"), "w") as f: f.write(hcl_code)
    
    return {"iac_code": f"{hcl_code}", "error_message": ""}


def visualization_tool(state: GraphState):
    logging.info("Executing visualization_tool...")
    if not state.get("iac_code") or state.get("error_message"):
        return {"iac_diagram_path": ""}
        
    iac_dir = state["work_dir"]
    # We use the external script for more robust diagramming
    script_path = os.path.join(os.path.dirname(__file__), "diagram_generator.py")
    process = subprocess.run(
        ["python", script_path, iac_dir],
        capture_output=True,
        text=True,
        check=False
    )

    error_log_path = os.path.join(iac_dir, "diagram_error.log")
    if process.returncode != 0 or os.path.exists(error_log_path):
        error_output = process.stderr
        if os.path.exists(error_log_path):
            with open(error_log_path, 'r') as f:
                error_output += f.read()
        logging.error(f"Diagram generation failed: {error_output}")
        return {"iac_diagram_path": ""}

    diagram_path = process.stdout.strip()
    if diagram_path and os.path.exists(diagram_path):
        # We need to return a path the frontend can access via the API
        relative_path = os.path.relpath(diagram_path, 'backend')
        api_accessible_path = f"/{relative_path.replace(os.path.sep, '/')}"
        return {"iac_diagram_path": api_accessible_path}
    
    return {"iac_diagram_path": ""}


def deployment_planning_tool(state: GraphState):
    logging.info("Executing deployment_planning_tool...")
    iac_dir = state["work_dir"]
    chdir_arg = f"-chdir={iac_dir}"
    
    # Run init first, suppressing output unless there's an error
    init_process = subprocess.run(["terraform", chdir_arg, "init", "-no-color", "-upgrade"], capture_output=True, text=True)
    if init_process.returncode != 0:
        return {"plan_output": f"Terraform Init Failed:\n{init_process.stderr}"}

    plan_process = subprocess.run(["terraform", chdir_arg, "plan", "-no-color"], capture_output=True, text=True)
    return {"plan_output": plan_process.stdout + "\n" + plan_process.stderr}


def execution_tool(state: GraphState):
    logging.info("Executing execution_tool...")
    iac_dir = state["work_dir"]
    chdir_arg = f"-chdir={iac_dir}"
    apply_process = subprocess.run(["terraform", chdir_arg, "apply", "-auto-approve", "-no-color"], capture_output=True, text=True)
    return {"apply_output": apply_process.stdout + "\n" + apply_process.stderr}

# Dummy clarification agent for now, can be built out later
def clarification_agent(state: GraphState):
    return {"clarification_questions": []}

def architectural_goal_node(state: GraphState):
    return {"initial_request": state["conversation_history"][-1].content, "clarification_questions": []}

def route_requests(state: GraphState):
    if state.get("error_message"):
        return END
    return "generate" if not state.get("clarification_questions") else END

# --- 3. GRAPH DEFINITION ---
def create_graph() -> StateGraph:
    workflow = StateGraph(GraphState)
    workflow.add_node("start_node", architectural_goal_node)
    workflow.add_node("clarification_agent", clarification_agent)
    workflow.add_node("generate_code", iac_generation_agent)
    workflow.add_node("generate_diagram", visualization_tool)

    workflow.set_entry_point("start_node")
    workflow.add_edge("start_node", "clarification_agent")
    workflow.add_conditional_edges("clarification_agent", route_requests, {"generate": "generate_code", END: END})
    workflow.add_edge("generate_code", "generate_diagram")
    workflow.add_edge("generate_diagram", END)
    
    return workflow.compile()

# Compile the graph once on startup
app_graph = create_graph()
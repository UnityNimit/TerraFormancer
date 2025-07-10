import os
import subprocess
import json
import io
import logging
from typing import TypedDict, List

from dotenv import load_dotenv
import hcl2
from langgraph.graph import StateGraph, END
from langchain_core.messages import BaseMessage
from langchain_google_genai import ChatGoogleGenerativeAI

load_dotenv()
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class GraphState(TypedDict):
    work_dir: str
    initial_request: str
    conversation_history: List[BaseMessage]
    
    intent: str               
    chat_response: str        
    
    iac_code: str
    iac_diagram_path: str
    plan_output: str
    apply_output: str
    clarification_questions: List[str]
    error_message: str

try:
    llm = ChatGoogleGenerativeAI(model="gemini-1.5-flash", temperature=0.1)
except Exception as e:
    logging.error(f"FATAL: Error initializing LLM. Please check your GOOGLE_API_KEY. Details: {e}")
    raise

def intent_router_node(state: GraphState):
    """
    Classifies the user's intent to decide which path the graph should take.
    This is the new entry point of our logic.
    """
    logging.info("Executing intent_router_node...")
    user_message = state['conversation_history'][-1].content
    
    prompt = f"""
    You are a master router for a DevOps AI assistant. Your job is to classify the user's latest message into one of two categories based on their intent.
    
    1.  `CODE_MODIFICATION`: The user wants to create, add, remove, change, update, or provision infrastructure. This includes requests for new resources like S3 buckets, EC2 instances, VPCs, etc.
    2.  `GENERAL_CHAT`: The user is asking a question, seeking an opinion, asking for an explanation, or having a general conversation. Examples: "What is a VPC?", "What's the best instance type for a web server?", "Thanks!", "Explain the diagram."

    Analyze the following user message:
    "{user_message}"

    Return ONLY the category name (`CODE_MODIFICATION` or `GENERAL_CHAT`). Do not add any other text.
    """
    response = llm.invoke(prompt)
    intent = response.content.strip()
    logging.info(f"User intent classified as: {intent}")
    return {"intent": intent}

def conversational_agent_node(state: GraphState):
    """
    Handles general questions and conversation. Does not generate code.
    """
    logging.info("Executing conversational_agent_node...")
    conversation_for_prompt = "\n".join([f"{msg.type}: {msg.content}" for msg in state['conversation_history']])

    prompt = f"""
    You are a friendly and knowledgeable DevOps assistant. Your user is asking a question or having a general conversation.
    Provide a helpful, concise, and friendly answer based on the conversation history. Do not generate code unless specifically asked to show an example snippet within your explanation.

    Conversation History:
    {conversation_for_prompt}

    Your Answer:
    """
    response = llm.invoke(prompt)
    return {"chat_response": response.content}


def architectural_goal_node(state: GraphState):
    """(This function is kept for reference but is no longer part of the main graph flow)"""
    return {"initial_request": state["conversation_history"][-1].content, "clarification_questions": []}



def iac_generation_agent(state: GraphState):
    logging.info("Executing iac_generation_agent: Architecting infrastructure...")
    aws_region = os.getenv("AWS_DEFAULT_REGION", "us-east-1")
    conversation_for_prompt = "\n".join([f"{msg.type}: {msg.content}" for msg in state['conversation_history']])
    existing_code = state.get("iac_code", "")

    if existing_code and "Error" not in existing_code:
        clean_existing_code = existing_code.replace("--- main.tf ---", "").strip()
        prompt = f"""
        You are an expert DevOps engineer who flawlessly modifies existing Terraform HCL code. Your task is to take an existing main.tf file and a user's request, and return a NEW, COMPLETE, and VALID main.tf file that incorporates the user's changes.
        *CRITICAL RULES:*
        1.  You MUST return the **entire, complete, and updated main.tf file**. Do not return snippets or explanations.
        2.  If adding a new resource that another resource depends on, you must add the new resource AND update the existing resource to reference it.
        3.  Resource names (e.g., aws_instance.web_server) must remain consistent unless the user asks to change them.
        ---
        *YOUR CURRENT TASK*
        *Full Conversation History:*
        {conversation_for_prompt}
        **Existing main.tf to modify:**
        ```hcl
        {clean_existing_code}
        ```
        Now, based on the last user message, return ONLY the full, updated, and raw HCL code for the new main.tf file.
        """
    else:
        prompt = f"""
        You are an expert DevOps engineer who writes lean, correct, and minimal Terraform HCL for AWS.
        Your task is to write a complete main.tf file from scratch that fulfills the user's request.
        *CRITICAL INSTRUCTIONS:*
        1.  *BE PRECISE:* Fulfill the user's request exactly as stated.
        2.  *NO EXTRAS:* Do *not* add extra resources unless they are explicitly requested.
        3.  *INCLUDE PROVIDER:* The AWS provider block MUST include the region. Use {aws_region}.
        4.  *HCL ONLY:* Return ONLY the raw HCL code, without any markdown fences or explanations.
        *Full Conversation History:*
        {conversation_for_prompt}
        Write the Terraform code now.
        """
    
    response = llm.invoke(prompt)
    hcl_code = response.content.strip().replace("```hcl", "").replace("```", "").strip()

    try:
        with io.StringIO(hcl_code) as f:
            hcl2.load(f)
        logging.info("HCL validation successful.")
    except Exception as e:
        error_msg = f"**Validation Error:** Agent produced invalid HCL. Details: {e}\n\n---\n{hcl_code}"
        logging.error(error_msg)
        return {"iac_code": "", "error_message": error_msg}

    if "provider" not in hcl_code and "terraform {" not in hcl_code:
        error_msg = f"Error: LLM returned invalid HCL (missing provider block).\n---\n{hcl_code}"
        logging.error(error_msg)
        return {"iac_code": "", "error_message": error_msg}
    
    iac_dir = state["work_dir"]
    with open(os.path.join(iac_dir, "main.tf"), "w") as f: f.write(hcl_code)
    
    return {"iac_code": f"{hcl_code}", "error_message": ""}


def clarification_agent(state: GraphState):
    logging.info("Executing clarification_agent: Analyzing request for details...")
    conversation_for_prompt = "\n".join([f"{msg.type}: {msg.content}" for msg in state['conversation_history']])
    
    prompt = f"""
    You are a meticulous Cloud Architecture requirement analyst. Your goal is to gather key details before any code is written.
    Analyze the user's last message in the context of the entire conversation:
    ---
    {conversation_for_prompt}
    ---
    *Your Task & Rules*:
    1.  For any new resource request (like aws_s3_bucket, aws_instance), you MUST check if a user-defined name is provided.
    2.  If a name for a key resource is missing, you MUST ask for it.
    3.  If you have enough information to proceed, you MUST return an empty list: [].
    4.  Output ONLY a raw JSON list of strings.
    *Example 1 (Info Missing):*
    User: "Create an EC2 instance"
    Your Output: ["What should I name the EC2 instance (e.g., 'web-server') and what instance_type should I use (e.g., 't2.micro')?"]
    *Example 2 (Info Sufficient):*
    User: "Create a t2.micro EC2 instance named 'api-server'."
    Your Output: []
    """
    
    response = llm.invoke(prompt)
    try:
        clarification_questions = json.loads(response.content)
        logging.info(f"Clarification questions found: {clarification_questions}")
        return {"clarification_questions": clarification_questions}
    except json.JSONDecodeError:
        logging.error(f"Failed to decode JSON from clarification agent. Response: {response.content}")
        return {"clarification_questions": []}


def visualization_tool(state: GraphState):
    logging.info("Executing visualization_tool...")
    if not state.get("iac_code") or state.get("error_message"): return {"iac_diagram_path": ""}
    iac_dir = state["work_dir"]
    script_path = os.path.join(os.path.dirname(__file__), "diagram_generator.py")
    process = subprocess.run(["python", script_path, iac_dir], capture_output=True, text=True, check=False)
    if process.returncode != 0: return {"iac_diagram_path": ""}
    diagram_path = process.stdout.strip()
    if diagram_path and os.path.exists(diagram_path):
        relative_path = os.path.relpath(diagram_path, 'backend')
        api_accessible_path = f"/{relative_path.replace(os.path.sep, '/')}"
        return {"iac_diagram_path": api_accessible_path}
    return {"iac_diagram_path": ""}

def deployment_planning_tool(state: GraphState):
    logging.info("Executing deployment_planning_tool...")
    iac_dir = state["work_dir"]
    chdir_arg = f"-chdir={iac_dir}"
    init_process = subprocess.run(["terraform", chdir_arg, "init", "-no-color", "-upgrade"], capture_output=True, text=True)
    if init_process.returncode != 0: return {"plan_output": f"Terraform Init Failed:\n{init_process.stderr}", "error_message": f"Terraform Init Failed:\n{init_process.stderr}"}
    plan_process = subprocess.run(["terraform", chdir_arg, "plan", "-no-color"], capture_output=True, text=True)
    return {"plan_output": plan_process.stdout + "\n" + plan_process.stderr}

def execution_tool(state: GraphState):
    logging.info("Executing execution_tool...")
    iac_dir = state["work_dir"]
    chdir_arg = f"-chdir={iac_dir}"
    apply_process = subprocess.run(["terraform", chdir_arg, "apply", "-auto-approve", "-no-color"], capture_output=True, text=True)
    return {"apply_output": apply_process.stdout + "\n" + apply_process.stderr}



def route_by_intent(state: GraphState):
    """This function decides the first major branch of the graph."""
    intent = state.get("intent")
    if intent == "CODE_MODIFICATION":
        logging.info("Routing to: Code Modification Pipeline")
        return "clarification_agent"
    
    logging.info("Routing to: General Chat")
    return "conversational_agent"

def route_after_clarification(state: GraphState):
    """This function decides if the code generation pipeline should proceed or stop for user input."""
    if state.get("error_message"):
        logging.warning("Error detected, ending graph execution.")
        return END

    if state.get("clarification_questions"):
        logging.info("Clarification questions exist. Ending graph to await user response.")
        return END
    
    logging.info("No clarification needed. Proceeding to code generation.")
    return "generate_code"


def create_graph() -> StateGraph:
    """
    Builds the state machine graph with intelligent routing.
    """
    workflow = StateGraph(GraphState)
    
    workflow.add_node("intent_router", intent_router_node)
    workflow.add_node("conversational_agent", conversational_agent_node)
    workflow.add_node("clarification_agent", clarification_agent)
    workflow.add_node("generate_code", iac_generation_agent)
    workflow.add_node("generate_diagram", visualization_tool)

    workflow.set_entry_point("intent_router")
    
    workflow.add_conditional_edges(
        "intent_router",
        route_by_intent,
        {
            "clarification_agent": "clarification_agent",    
            "conversational_agent": "conversational_agent" 
        }
    )
    
    workflow.add_edge("conversational_agent", END)
    
    workflow.add_conditional_edges(
        "clarification_agent",
        route_after_clarification,
        {
            "generate_code": "generate_code", 
            END: END                          
        }
    )
    
    workflow.add_edge("generate_code", "generate_diagram")
    workflow.add_edge("generate_diagram", END)
    
    return workflow.compile()

app_graph = create_graph()

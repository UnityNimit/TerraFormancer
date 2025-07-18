import os
import subprocess
import json
import io
import logging
from typing import TypedDict, List
from datetime import datetime, timedelta

from dotenv import load_dotenv
import hcl2
from langgraph.graph import StateGraph, END
from langchain_core.messages import BaseMessage
from langchain_google_genai import ChatGoogleGenerativeAI
import boto3

# Load environment variables
load_dotenv()
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Define the state for our graph
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

# Initialize the LLM
try:
    llm = ChatGoogleGenerativeAI(model="gemini-1.5-flash", temperature=0.1)
except Exception as e:
    logging.error(f"FATAL: Error initializing LLM. Please check your GOOGLE_API_KEY. Details: {e}")
    raise

# --- TOOL DEFINITIONS ---

def aws_sdk_tool(resource_id: str, metric: str, namespace: str, dimensions: list) -> dict:
    """
    A tool to fetch CloudWatch metrics for a given AWS resource.
    Returns a dictionary with the data or an error message.
    """
    logging.info(f"Executing aws_sdk_tool for resource:'{resource_id}' metric:'{metric}'")
    try:
        # Ensure your environment has AWS credentials configured (e.g., via ~/.aws/credentials)
        client = boto3.client('cloudwatch')
        response = client.get_metric_statistics(
            Namespace=namespace,
            MetricName=metric,
            Dimensions=dimensions,
            StartTime=datetime.utcnow() - timedelta(hours=3),  # Check the last 3 hours
            EndTime=datetime.utcnow(),
            Period=300,  # 5-minute intervals
            Statistics=['Average', 'Maximum'],
        )
        # Return a clean summary of datapoints, sorted by time
        datapoints = sorted(response.get('Datapoints', []), key=lambda x: x['Timestamp'])
        return {"status": "success", "data": datapoints}
    except Exception as e:
        logging.error(f"boto3 tool error: {e}")
        # Return a structured error that the LLM can understand
        return {"status": "error", "message": f"An error occurred while fetching metrics: {str(e)}"}

# --- AGENT NODE DEFINITIONS ---

def intent_router_node(state: GraphState):
    """
    Classifies the user's intent to decide which path the graph should take.
    This is the new entry point of our logic, now with three categories.
    """
    logging.info("Executing intent_router_node...")
    user_message = state['conversation_history'][-1].content

    prompt = f"""
    You are a master router for a DevOps AI assistant. Classify the user's latest message into one of three categories:

    1.  `CODE_MODIFICATION`: The user wants to create, add, remove, change, or deploy infrastructure.
        (Examples: "Create an S3 bucket", "Add an EC2 instance", "deploy my changes")
    2.  `DEBUGGING_INQUIRY`: The user is asking a question about the status, health, or performance of a *specific, named* cloud resource.
        (Examples: "Why is my instance i-012345abcdef slow?", "What's the status of the main database?", "Is the web server getting any traffic?")
    3.  `GENERAL_CHAT`: The user is asking a general question, seeking an explanation, or having a conversation not tied to a specific, live resource.
        (Examples: "What is a VPC?", "Thanks!", "Explain the diagram.")

    Analyze the following user message:
    "{user_message}"

    Return ONLY the category name (`CODE_MODIFICATION`, `DEBUGGING_INQUIRY`, or `GENERAL_CHAT`).
    """
    response = llm.invoke(prompt)
    intent = response.content.strip()
    logging.info(f"User intent classified as: {intent}")
    return {"intent": intent}


# In agent_logic.py, replace the old debugging_agent with this one.

def debugging_agent(state: GraphState):
    """
    Handles debugging inquiries by using tools to fetch live data and analyzing it.
    This version has improved NLU with conversation history.
    """
    logging.info("Executing debugging_agent...")
    
    # --- IMPROVEMENT 1: Use the whole conversation history for context ---
    conversation_for_prompt = "\n".join([f"{msg.type}: {msg.content}" for msg in state['conversation_history']])

    # --- IMPROVEMENT 2: A much more robust NLU prompt ---
    nlu_prompt = f"""
    You are an expert at extracting key information from a user's request for monitoring.
    Your goal is to fill a JSON object based on the **entire conversation history**.

    Analyze the conversation below. Identify the 'resource_id' (e.g., an instance ID) and infer the appropriate CloudWatch 'metric', 'namespace', and 'dimension_key'.
    - If the user mentions slowness, high load, or performance, the metric is 'CPUUtilization'. The namespace for EC2 is 'AWS/EC2' and the dimension key is 'InstanceId'.
    - If the user provides just an ID in their last message, use the context from the previous messages to fill in the other details.
    - If you cannot determine a value for a key, use `null`.

    Conversation History:
    ---
    {conversation_for_prompt}
    ---

    Return a clean, raw JSON object with the keys: "resource_id", "metric", "namespace", "dimension_key". Do NOT use markdown fences like ```json.
    """
    nlu_response = llm.invoke(nlu_prompt)
    
    # Add logging to see exactly what the LLM returned
    logging.info(f"NLU Raw Response: {nlu_response.content}")

    try:
        # --- IMPROVEMENT 3: Clean the LLM response before parsing ---
        cleaned_response = nlu_response.content.strip().replace("```json", "").replace("```", "").strip()
        entities = json.loads(cleaned_response)

        resource_id = entities.get('resource_id')
        metric = entities.get('metric')
        namespace = entities.get('namespace')
        dimension_key = entities.get('dimension_key')

        # Check for missing essential information
        if not all([resource_id, metric, namespace, dimension_key]):
             raise ValueError("Essential information for monitoring is missing.")

        dimensions = [{'Name': dimension_key, 'Value': resource_id}]

    except (json.JSONDecodeError, KeyError, ValueError) as e:
        logging.error(f"Failed to parse entities or essential info missing: {e}")
        return {"chat_response": "I'm sorry, I still need more information to proceed. Could you please specify the full resource ID and what you'd like to check (e.g., 'check CPU for i-012345abcdef')?"}

    # --- Step 2 & 3 (Tool Use and Reasoning) remain the same ---
    tool_data = aws_sdk_tool(resource_id, metric, namespace, dimensions)

    reasoning_prompt = f"""
    You are a Senior DevOps Engineer. You are helping a user debug a problem with their cloud infrastructure.
    - User's Question: "{state['conversation_history'][-1].content}"
    - You have just fetched the following monitoring data from AWS CloudWatch:
      {json.dumps(tool_data, indent=2, default=str)}

    Analyze this data and provide a helpful, clear, and concise response.
    - If the tool status is 'error', explain the error to the user and ask them to check if the resource ID is correct and if the application has the right permissions.
    - If the data array is empty, state that no metrics were found for that resource in the last 3 hours and ask them to verify the resource ID and region.
    - If there is data, analyze it. Look for trends, especially high average or maximum values (e.g., CPUUtilization > 80%).
    - Provide a summary of your findings and suggest a concrete next step (e.g., "The CPU has been consistently high. You may want to consider upgrading the instance type.").
    """
    final_response = llm.invoke(reasoning_prompt)
    return {"chat_response": final_response.content}


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
        cleaned_response = response.content.strip().replace("```json", "").replace("```", "").strip()
        clarification_questions = json.loads(cleaned_response)
        logging.info(f"Clarification questions found: {clarification_questions}")
        return {"clarification_questions": clarification_questions}
    except json.JSONDecodeError:
        logging.error(f"Failed to decode JSON from clarification agent. Response: {response.content}")
        return {"clarification_questions": []}

# --- NON-AGENT TOOL AND ROUTING FUNCTIONS ---

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
    """This function decides the first major branch of the graph based on intent."""
    intent = state.get("intent")
    if intent == "CODE_MODIFICATION":
        logging.info("Routing to: Code Modification Pipeline")
        return "clarification_agent"
    if intent == "DEBUGGING_INQUIRY":
        logging.info("Routing to: Debugging Agent")
        return "debugging_agent"
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


# --- GRAPH DEFINITION ---

def create_graph() -> StateGraph:
    """
    Builds the state machine graph with intelligent routing.
    """
    workflow = StateGraph(GraphState)

    # Add all nodes to the graph
    workflow.add_node("intent_router", intent_router_node)
    workflow.add_node("conversational_agent", conversational_agent_node)
    workflow.add_node("debugging_agent", debugging_agent)
    workflow.add_node("clarification_agent", clarification_agent)
    workflow.add_node("generate_code", iac_generation_agent)
    workflow.add_node("generate_diagram", visualization_tool)

    # Set the entry point
    workflow.set_entry_point("intent_router")

    # Define the edges and conditional routes
    workflow.add_conditional_edges(
        "intent_router",
        route_by_intent,
        {
            "clarification_agent": "clarification_agent",
            "conversational_agent": "conversational_agent",
            "debugging_agent": "debugging_agent"
        }
    )

    # Define terminal nodes for chat-like interactions
    workflow.add_edge("conversational_agent", END)
    workflow.add_edge("debugging_agent", END)

    # Define the code generation pipeline
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

    # Compile the graph
    return workflow.compile()


# Instantiate the graph
app_graph = create_graph()
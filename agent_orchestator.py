import autogen
from mcp_tools_bridge import (
    scrape_candidate_data, 
    enrich_candidate_email, 
    mcp_schedule_interview, 
    query_company_policies, 
    update_ats_database,
    mock_greenhouse_ats,
    send_email_notification
)
from llm_manager import get_rotated_groq_llm, execute_with_healing

# Conversational Memory Dictionary
session_memory = {}

GROQ_TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "scrape_candidate_data",
            "description": "Scrapes LinkedIn for candidate data.",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "enrich_candidate_email",
            "description": "Finds a candidate's professional email address. ALWAYS use this before sending an email if the email is unknown.",
            "parameters": {
                "type": "object",
                "properties": {
                    "first_name": {"type": "string"},
                    "last_name": {"type": "string"},
                    "company_domain": {"type": "string", "description": "The website domain of their current company (e.g., google.com)"}
                },
                "required": ["first_name", "last_name", "company_domain"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "update_ats_database",
            "description": "Updates the PostgreSQL database. Use status: 'Pending', 'Interviewing', 'Selected', or 'Rejected'.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "status": {"type": "string"},
                    "expected_salary": {"type": "string"},
                    "role": {"type": "string"}
                },
                "required": ["name", "status", "expected_salary", "role"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "mcp_schedule_interview",
            "description": "Interacts with Google Calendar MCP to schedule interviews.",
            "parameters": {
                "type": "object",
                "properties": {
                    "candidate_email": {"type": "string"},
                    "time_slot": {"type": "string"}
                },
                "required": ["candidate_email", "time_slot"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "send_email_notification",
            "description": "Sends dynamic emails to candidates.",
            "parameters": {
                "type": "object",
                "properties": {
                    "candidate_email": {"type": "string"},
                    "subject": {"type": "string"},
                    "body": {"type": "string"}
                },
                "required": ["candidate_email", "subject", "body"]
            }
        }
    },
    # --- NEW SCHEMA: Adding the RAG query tool for the OfferNegotiator ---
    {
        "type": "function",
        "function": {
            "name": "query_company_policies",
            "description": "Uses RAG to answer candidate questions about company culture, policies, or salary bands.",
            "parameters": {
                "type": "object",
                "properties": {"question": {"type": "string"}},
                "required": ["question"]
            }
        }
    }
]

def get_autogen_config(include_tools: bool = True):
    """
    DYNAMIC CONFIG GENERATOR: 
    Workers get the toolbelt; the GroupChatManager moderator gets a clean config.
    """
    import os
    from dotenv import load_dotenv
    load_dotenv(override=True)
    
    config = {
        "config_list": [{
            "model": "llama-3.3-70b-versatile", 
            "api_key": os.getenv("ACTIVE_GROQ_KEY").strip(),
            "base_url": "https://api.groq.com/openai/v1",
            "api_type": "openai"
        }],
        "temperature": 0.2,
    }
    
    if include_tools:
        config["tools"] = GROQ_TOOL_SCHEMAS
        
    return config

def create_talent_agents():
    worker_config = get_autogen_config(include_tools=True)
    
    sourcing_bot = autogen.AssistantAgent(
        name="SourcingBot",
        description="Call this agent FIRST. Its only job is to use the scrape_candidate_data tool to find a candidate.",
        system_message="You are an elite Tech Sourcer. Use the scrape_candidate_data tool to find passive candidates. Extract their first name, last name, and current company domain. Once you have this data, output the summary.",
        llm_config=worker_config,
    )
    
    candidate_liaison = autogen.AssistantAgent(
        name="CandidateLiaison",
        description="Call this agent AFTER SourcingBot finds a candidate. It runs the enrichment tool, updates the database, and sends emails.",
        system_message=(
            "You are the Candidate Liaison. You engage candidates and execute system updates. "
            "CRITICAL TOOL INSTRUCTIONS: "
            "1. Before sending an email, you MUST use the 'enrich_candidate_email' tool to get their real email address. "
            "2. When scheduling, you MUST use the mcp_schedule_interview tool with EXACTLY two arguments: 'candidate_email' and 'time_slot'. "
            "3. After a tool returns SUCCESS, reply with plain text. DO NOT generate another raw JSON tool call."
        ),
        llm_config=worker_config,
    )
    
    offer_negotiator = autogen.AssistantAgent(
        name="OfferNegotiator",
        description="Call this agent to handle Selected/Rejected decisions, negotiate offers, and update the ATS.",
        system_message="You draft offers and update the ATS database. Analyze salary bands. Use update_ats_database tool to mark them as 'Selected' or 'Rejected'. You can use query_company_policies to check benefits and guidelines before sending offers.",
        llm_config=worker_config,
    )

    user_proxy = autogen.UserProxyAgent(
        name="HR_Manager",
        human_input_mode="NEVER",
        max_consecutive_auto_reply=5,
        code_execution_config=False,
        function_map={
            "scrape_candidate_data": scrape_candidate_data.func,
            "enrich_candidate_email": enrich_candidate_email.func,
            "update_ats_database": update_ats_database.func,
            "mcp_schedule_interview": mcp_schedule_interview.func,
            "send_email_notification": send_email_notification.func,
            "query_company_policies": query_company_policies.func # --- NEW MAP: Allow execution of the tool ---
        }
    )
    
    return user_proxy, sourcing_bot, candidate_liaison, offer_negotiator


def run_recruitment_workflow(job_description: str, session_id: str):
    """PHASE 1: Sourcing and Scheduling ONLY."""
    past_context = session_memory.get(session_id, "")
    base_prompt = f"Previous Context: {past_context}\n\nTask: {job_description}"

    def execute_chat():
        user_proxy, sourcer, liaison, _ = create_talent_agents()
        
        groupchat = autogen.GroupChat(
            agents=[user_proxy, sourcer, liaison], 
            messages=[], 
            max_round=30
        )
        
        manager = autogen.GroupChatManager(
            groupchat=groupchat, 
            llm_config=get_autogen_config(include_tools=False)
        )

        # --- SELF-HEALING LOOP PROTOCOL (PHASE 1) ---
        current_prompt = base_prompt
        for attempt in range(3):
            try:
                user_proxy.initiate_chat(manager, message=current_prompt)
                return groupchat.messages
            except Exception as execution_error:
                print(f"⚠️ [SELF-HEALING PROMPT PROTOCOL] Internal crash detected on attempt {attempt + 1}: {str(execution_error)}")
                if attempt == 2:
                    raise execution_error 
                
                current_prompt = (
                    f"⚠️ [SYSTEM SELF-HEALING OVERRIDE] Your previous attempt crashed with the following error:\n"
                    f"'{str(execution_error)}'\n\n"
                    f"Analyze what caused this crash (e.g., incorrect arguments, wrong tool recipient, syntax error). "
                    f"Fix your approach instantly and proceed with the core request accurately:\n{base_prompt}"
                )
                groupchat.messages = []

    messages = execute_with_healing(execute_chat)
    session_memory[session_id] = "\n".join([msg.get("content", "") for msg in messages if msg.get("content")])
    return session_memory[session_id]


def process_interview_result(name: str, email: str, role: str, decision: str, session_id: str):
    """PHASE 2: Triggered by Human UI."""
    
    # --- NEW LOGIC: Dynamic prompt based on whether they were selected or rejected ---
    if decision.lower() == "selected":
        base_prompt = (
            f"HR DECISION: The candidate {name} ({email}) applied for {role} and has been SELECTED. "
            f"OfferNegotiator, you MUST execute these tools in exact order: "
            f"1. Use 'update_ats_database' to mark their status as 'Selected'. "
            f"2. Use 'query_company_policies' to search for 'core benefits, work hours, and onboarding'. "
            f"3. Use 'send_email_notification' to send the final offer letter. In the body of the email, warmly welcome them and summarize the company policies you retrieved from the RAG tool."
        )
    else:
        base_prompt = (
            f"HR DECISION: The candidate {name} ({email}) applied for {role} and has been {decision.upper()}. "
            f"You MUST use your tools to update the ATS database status to '{decision.title()}' and send them an email notification right now."
        )

    def execute_chat():
        user_proxy, _, liaison, negotiator = create_talent_agents()
        
        # Select the single correct agent for the job
        target_agent = negotiator if decision.lower() == "selected" else liaison

        # --- SELF-HEALING LOOP PROTOCOL (PHASE 2) ---
        current_prompt = base_prompt
        for attempt in range(3):
            try:
                # DIRECT COMMUNICATION: We bypass the GroupChat entirely for 1-on-1 tasks!
                user_proxy.initiate_chat(target_agent, message=current_prompt, clear_history=True)
                
                # Retrieve the conversation history directly between these two agents
                messages = user_proxy.chat_messages[target_agent]
                return messages
            except Exception as execution_error:
                print(f"⚠️ [SELF-HEALING] Crash detected on attempt {attempt + 1}: {str(execution_error)}")
                if attempt == 2:
                    raise execution_error
                
                current_prompt = (
                    f"⚠️ [SYSTEM SELF-HEALING OVERRIDE] Your previous attempt crashed:\n"
                    f"'{str(execution_error)}'\n\n"
                    f"Fix the error, DO NOT hallucinate, and execute the following task:\n{base_prompt}"
                )

    messages = execute_with_healing(execute_chat)
    return "\n".join([msg.get("content", "") for msg in messages if msg.get("content")])
import os
import dotenv
from langchain_groq import ChatGroq
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

class GroqAuthException(Exception): pass

def get_rotated_groq_llm():
    dotenv.load_dotenv(override=True)
    active_key = os.environ.get("ACTIVE_GROQ_KEY")
    return ChatGroq(
        temperature=0.2, 
        model_name="llama3-70b-8192", 
        groq_api_key=active_key
    )

def rotate_api_key():
    dotenv.load_dotenv(override=True)
    active_key = os.environ.get("ACTIVE_GROQ_KEY", "").strip()
    pool_str = os.environ.get("GROQ_KEY_POOL", "")
    
    # Strip spaces to ensure perfect matching
    pool = [k.strip() for k in pool_str.split(",") if k.strip()]
    
    if not pool:
        raise ValueError("No keys left in pool!")
        
    try:
        current_idx = pool.index(active_key)
        next_idx = (current_idx + 1) % len(pool)
    except ValueError:
        next_idx = 0
        
    new_key = pool[next_idx]
    
    # 1. Write back to physical .env file
    env_file = dotenv.find_dotenv()
    if env_file:
        dotenv.set_key(env_file, "ACTIVE_GROQ_KEY", new_key)
    
    # 2. CRITICAL FIX: Update the live Python memory environment!
    os.environ["ACTIVE_GROQ_KEY"] = new_key
    
    print(f"[HEALING PROTOCOL] Rotated Groq API Key to ending in ...{new_key[-4:]}")
    return new_key

def execute_with_healing(agent_function, *args, **kwargs):
    """Wrapper to execute LLM calls with automatic key rotation on failure."""
    pool_str = os.environ.get("GROQ_KEY_POOL", "")
    max_retries = len([k for k in pool_str.split(",") if k.strip()]) or 1
    
    for attempt in range(max_retries):
        try:
            return agent_function(*args, **kwargs)
        except Exception as e:
            error_msg = str(e).lower()
            if "401" in error_msg or "429" in error_msg or "rate limit" in error_msg:
                print(f"API Error detected: {str(e)}. Triggering self-healing key rotation...")
                rotate_api_key()
            else:
                raise e
    raise Exception("All Groq API keys in the pool have been exhausted or rate-limited.")
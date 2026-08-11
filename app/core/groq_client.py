import os
from typing import Type, TypeVar, cast
from dotenv import load_dotenv
from langchain_groq import ChatGroq
from pydantic import SecretStr, BaseModel

load_dotenv()

T = TypeVar("T", bound=BaseModel)

_raw_keys = [os.getenv("GROQ_API_KEY"), os.getenv("GROQ_API_KEY_2")]
GROQ_KEYS = [k for k in _raw_keys if k]

if not GROQ_KEYS:
    raise RuntimeError("No Groq API keys configured - set GROQ_API_KEY in .env")

_llm_cache = {}


def _get_llm(key_index: int, model: str) -> ChatGroq:
    cache_key = (key_index, model)
    if cache_key not in _llm_cache:
        _llm_cache[cache_key] = ChatGroq(
            model=model,
            api_key=cast(SecretStr, GROQ_KEYS[key_index]),
            max_retries=0,  # fail fast on rate limits - let OUR rotation
                             # handle it instantly instead of the client
                             # silently retrying/waiting ~26s internally first
        )
    return _llm_cache[cache_key]


def _is_rate_limit_error(e: Exception) -> bool:
    msg = str(e).lower()
    return "rate_limit" in msg or "429" in msg or "quota" in msg


def invoke_structured(schema_class: Type[T], prompt: str, model: str = "llama-3.3-70b-versatile") -> T:
    """
    Calls Groq with structured output, automatically rotating to the next
    configured API key if the current one is rate-limited - continuing the
    exact same task on the next key rather than failing. Only raises once
    every configured key has been exhausted.
    """
    last_error = None
    for i, key in enumerate(GROQ_KEYS):
        llm = _get_llm(i, model)
        structured_llm = llm.with_structured_output(schema_class, method="json_mode")
        try:
            return cast(T, structured_llm.invoke(prompt))
        except Exception as e:
            if _is_rate_limit_error(e):
                print(f"[groq_client] API key #{i+1} rate-limited, switching to next key...")
                last_error = e
                continue
            raise  # non-rate-limit errors surface immediately, not swallowed

    if last_error is not None:
        raise last_error
    raise RuntimeError("All Groq API keys exhausted, but no error was captured.")
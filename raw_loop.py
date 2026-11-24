"""Steps 2-3: a hand-written tool-calling loop with real web tools.

The model never runs any code. It only *asks* for a tool call. Our code runs
the function and sends the result back.
"""
import os

import httpx
import trafilatura
from dotenv import load_dotenv
from google import genai
from google.genai import types
from tavily import TavilyClient

load_dotenv()  # reads GOOGLE_API_KEY, TAVILY_API_KEY (and optional GEMINI_MODEL)

MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")
MAX_STEPS = 5
QUESTION = (
    "What is the latest stable version of Python? "
    "Cite the URLs you used."
)


# --- The tools: normal Python functions ------------------------------------
MAX_PAGE_CHARS = 4000  # keep fetched pages small so they fit the context window


def web_search(query: str) -> list[dict]:
    """Search the web with Tavily. Returns title, url and snippet per result."""
    try:
        response = TavilyClient().search(query, max_results=5)  # reads TAVILY_API_KEY
    except Exception as error:  # return the error so the model can react to it
        return [{"error": f"Search failed: {error}"}]
    return [
        {"title": r["title"], "url": r["url"], "snippet": r["content"]}
        for r in response["results"]
    ]


def fetch_url(url: str) -> str:
    """Download a page and return its readable text, cut to MAX_PAGE_CHARS."""
    try:
        page = httpx.get(url, follow_redirects=True, timeout=15.0)
        page.raise_for_status()
    except Exception as error:
        return f"Fetch failed: {error}"
    text = trafilatura.extract(page.text) or ""  # strips menus, ads and scripts
    if not text:
        return "Fetch failed: no readable text found on this page."
    return text[:MAX_PAGE_CHARS]


TOOLS = {"web_search": web_search, "fetch_url": fetch_url}  # name -> function

# --- The tool descriptions: all the model sees of each tool -----------------
# The model picks tools by reading these, so they say what each tool does and
# when to use it.
web_search_declaration = types.FunctionDeclaration(
    name="web_search",
    description=(
        "Search the web. Returns up to 5 results, each with a title, URL and "
        "short snippet. Use this first to find sources for a question. "
        "Snippets are brief, so call fetch_url on a promising result to read it."
    ),
    parameters_json_schema={
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "The search query"},
        },
        "required": ["query"],
    },
)

fetch_url_declaration = types.FunctionDeclaration(
    name="fetch_url",
    description=(
        "Download one web page and return its readable text, cut to about "
        "4,000 characters. Use this to read a page found by web_search before "
        "relying on it. Only pass URLs that came from web_search results."
    ),
    parameters_json_schema={
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "Full URL of the page"},
        },
        "required": ["url"],
    },
)

# Turn off the SDK's built-in automatic tool running, so WE run the loop.
config = types.GenerateContentConfig(
    tools=[
        types.Tool(function_declarations=[web_search_declaration, fetch_url_declaration])
    ],
    automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
)


def run_tool_call(call: types.FunctionCall) -> types.Part:
    """Run the function the model asked for and wrap the result for the model."""
    result = TOOLS[call.name](**call.args)  # <-- the tool actually runs HERE
    preview = str(result)[:150].replace("\n", " ")
    print(f"  tool call: {call.name}({dict(call.args)})")
    print(f"    -> {preview}...")
    return types.Part.from_function_response(
        name=call.name, response={"result": result}
    )


def main() -> None:
    client = genai.Client()  # picks up GOOGLE_API_KEY from the environment
    # The message history. It is re-sent on every step because the model
    # remembers nothing between calls.
    history = [types.Content(role="user", parts=[types.Part(text=QUESTION)])]
    print(f"Question: {QUESTION}\nModel: {MODEL}\n")

    for step in range(1, MAX_STEPS + 1):
        print(f"Step {step}: sending {len(history)} message(s) to the model")
        response = client.models.generate_content(
            model=MODEL, contents=history, config=config
        )
        reply = response.candidates[0].content
        history.append(reply)  # keep the model's reply in the history

        calls = [p.function_call for p in reply.parts if p.function_call]
        if not calls:  # no tool requested -> this is the final answer
            print(f"\nFinal answer: {response.text}")
            return

        # Run every requested tool and send all results back as one message.
        results = [run_tool_call(call) for call in calls]
        history.append(types.Content(role="user", parts=results))

    print(f"\nStopped: hit the {MAX_STEPS}-step limit without a final answer.")


if __name__ == "__main__":
    main()

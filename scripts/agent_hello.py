import json
import os

from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv(override=True)

client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")

# 1. Fake data and tools (the agent's "hands")
SUPPLIERS = [
    {"vendor": "OfficeMax Pro", "item": "printer paper (case)", "price": 42.00},
    {"vendor": "PaperDirect", "item": "printer paper (case)", "price": 38.50},
    {"vendor": "BulkSupplies Co", "item": "printer paper (case)", "price": 40.25},
]


def search_suppliers(item: str) -> list:
    return [s for s in SUPPLIERS if item.lower() in s["item"].lower()]


def get_budget() -> dict:
    return {"monthly_budget": 500.00, "spent_this_month": 120.00}


TOOL_FUNCTIONS = {
    "search_suppliers": lambda args: search_suppliers(args["item"]),
    "get_budget": lambda args: get_budget(),
}

# 2. Tell the model what tools exist
TOOLS = types.Tool(
    function_declarations=[
        {
            "name": "search_suppliers",
            "description": "Find supplier quotes for an item.",
            "parameters": {
                "type": "object",
                "properties": {
                    "item": {"type": "string", "description": "Item to search for, e.g. 'printer paper'"}
                },
                "required": ["item"],
            },
        },
        {
            "name": "get_budget",
            "description": "Get the business's monthly budget and spending so far.",
        },
    ]
)

CONFIG = types.GenerateContentConfig(
    system_instruction="You are a procurement assistant. Use tools to find the best option.",
    tools=[TOOLS],
    # We run tools ourselves so we stay in control (the policy engine needs this)
    automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
)


# 3. The agent loop
def run_agent(task: str) -> str:
    contents = [types.Content(role="user", parts=[types.Part(text=task)])]

    while True:
        response = client.models.generate_content(
            model=MODEL, contents=contents, config=CONFIG
        )
        contents.append(response.candidates[0].content)

        calls = response.function_calls
        if not calls:  # no tool requested -> final answer
            return response.text

        result_parts = []
        for call in calls:
            args = dict(call.args or {})
            print(f"  [tool] {call.name}({json.dumps(args)})")
            output = TOOL_FUNCTIONS[call.name](args)
            result_parts.append(
                types.Part.from_function_response(
                    name=call.name, response={"result": output}
                )
            )
        contents.append(types.Content(role="user", parts=result_parts))


if __name__ == "__main__":
    print(run_agent("I need to buy a case of printer paper. What's the best deal, and can I afford it?"))
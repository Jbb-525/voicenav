"""
Planner: Uses LLM to decide actions based on user input and page state
"""
from openai import OpenAI
from pydantic import BaseModel, Field
from typing import Union, Literal, Dict, Any
import os
from dotenv import load_dotenv

load_dotenv()


# Define specific action types
class GotoAction(BaseModel):
    """Navigate to a URL"""
    type: Literal["goto"]
    url: str = Field(description="URL to navigate to")


class ClickAction(BaseModel):
    """Click an element"""
    type: Literal["click"]
    target: str = Field(description="Element name to click (from accessibility tree)")


class TypeAction(BaseModel):
    """Type text into an input field"""
    type: Literal["type"]
    target: str = Field(description="Input field name (from accessibility tree)")
    text: str = Field(description="Text to type")
    submit: bool = Field(default=False, description="Press Enter after typing")


class ScrollAction(BaseModel):
    """Scroll the page"""
    type: Literal["scroll"]
    direction: Literal["up", "down"] = Field(description="Scroll direction")


class DoneAction(BaseModel):
    """Task completed"""
    type: Literal["done"]


# Union of all action types
Action = Union[GotoAction, ClickAction, TypeAction, ScrollAction, DoneAction]


class PlannerOutput(BaseModel):
    """Complete planner output with reasoning"""
    thought: str = Field(description="Step-by-step reasoning about what to do")
    action: Action = Field(description="The action to execute")


class Planner:
    """LLM-based planner for web automation"""
    
    def __init__(self, model: str = "gpt-4o-mini"):
        self.model = model
        self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        
        self.system_prompt = """You are a web automation agent. Your job is to help users navigate and interact with web pages.

You receive:
1. User's intent (what they want to do)
2. Current page state (URL, title, and interactive elements from Accessibility Tree)

Interactive elements format:
- role: Element type (button, link, textbox, combobox, etc.)
- name: Element's accessible name (visible text or label)
- value: Current value (for inputs)

Available actions:

1. goto: Navigate to a URL
   Fields: type="goto", url="https://example.com"

2. click: Click an element
   Fields: type="click", target="element name from list"

3. type: Input text into a field
   Fields: type="type", target="element name", text="text to type", submit=true/false
   - submit=true: press Enter after typing
   - submit=false: just type without submitting

4. scroll: Scroll the page
   Fields: type="scroll", direction="up" or "down"

5. done: Task complete
   Fields: type="done"

CRITICAL RULES:
- ONLY use elements from the interactive_elements list
- The "target" field MUST exactly match an element's "name" field
- For search: use type action with submit=true (don't click buttons)
- Think step by step
- Be precise

Example:
User: "search for cats"
Page has: [combobox] name: 'Search'

Response:
{
  "thought": "I see a search box named 'Search'. I'll type 'cats' and submit.",
  "action": {
    "type": "type",
    "target": "Search",
    "text": "cats",
    "submit": true
  }
}"""

    def decide(self, user_input: str, page_state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Decide what action to take
        
        Args:
            user_input: User's intent/command
            page_state: Current page state from Executor
            
        Returns:
            Action dictionary
        """
        formatted_state = self._format_page_state(page_state)
        
        user_message = f"""Current page:
{formatted_state}

User intent: {user_input}

Think step by step and decide the action."""

        print(f"\n🤔 Planning action for: '{user_input}'")
        print(f"   Current page: {page_state['url']}")
        
        try:
            response = self.client.beta.chat.completions.parse(
                model=self.model,
                messages=[
                    {"role": "system", "content": self.system_prompt},
                    {"role": "user", "content": user_message}
                ],
                response_format=PlannerOutput,
                temperature=0
            )
            
            output = response.choices[0].message.parsed
            
            # Convert Pydantic model to dict
            action_dict = output.action.model_dump()
            
            result = {
                'thought': output.thought,
                'action': action_dict
            }
            
            print(f"\n💭 Thought: {result['thought']}")
            print(f"🎯 Action: {result['action']}")
            
            return result
            
        except Exception as e:
            print(f"❌ Planning failed: {e}")
            import traceback
            traceback.print_exc()
            
            return {
                'thought': f'Error: {str(e)}',
                'action': {'type': 'done'}
            }
    
    def _format_page_state(self, page_state: Dict[str, Any]) -> str:
        """Format page state for LLM"""
        url = page_state.get('url', 'Unknown')
        title = page_state.get('title', 'Unknown')
        elements = page_state.get('interactive_elements', [])
        
        elements_text = "\n".join([
            f"  [{elem['role']}] name: '{elem['name']}'{f', value: \"{elem['value']}\"' if elem.get('value') else ''}"
            for elem in elements[:30]
        ])
        
        return f"""URL: {url}
Title: {title}

Interactive Elements ({len(elements)} total):
{elements_text}"""
"""
Planner: Uses LLM to decide actions based on user input and page state
"""
from openai import OpenAI
from pydantic import BaseModel, Field
from typing import Union, Literal, Dict, Any, List, Optional
import os
from dotenv import load_dotenv
import importlib.resources

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

class SelectAction(BaseModel):
    type: Literal["select"]
    dropdown: str 
    option: str


# Union of all action types
Action = Union[GotoAction, ClickAction, TypeAction, ScrollAction, DoneAction, SelectAction]
class PlannerOutput(BaseModel):
    """Complete planner output with hierarchical planning"""
    
    overall_plan: List[str] = Field(
        description="Step-by-step plan to achieve the user's goal (5-7 steps). Each step should be clear and verifiable."
    )
    
    current_step: int = Field(
        description="Which step in the plan we're currently executing (1-indexed). 0 means planning phase."
    )
    
    thought: str = Field(
        description="Detailed reasoning about the current situation and what to do next"
    )
    
    action: Action = Field(
        description="The specific action to execute right now"
    )
    
    plan_adjustment: Optional[str] = Field(
        default=None,
        description="If the plan needs adjustment based on what we observe, explain why"
    )


class Planner:
    """LLM-based planner for web automation"""
    
    def __init__(self, model: str = "gpt-4o"):
        self.model = model
        self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

        self.system_prompt = self._load_system_prompt()

    def _load_system_prompt(self) -> str:
        """load prompt from md file"""
        try:
            with (
                importlib.resources.files('prompt')
                .joinpath('system_prompt.md')
                .open('r', encoding='utf-8') as f
            ):
                return f.read().strip()
        except Exception as e:
            raise RuntimeError(f'Failed to load planner system prompt: {e}')
        
    def decide(
        self, 
        user_goal: str, 
        page_state: Dict[str, Any],
        action_history: List[Dict[str, Any]] = None,
        visual_context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Decide what action to take using hierarchical planning
        
        Args:
            user_goal: User's objective
            page_state: Current page state from Executor
            action_history: List of previous actions and results
            
        Returns:
            Action dictionary with plan, thought, and action
        """
        if action_history is None:
            action_history = []
        
        # Format components
        history_text = self._format_history(action_history)
        state_text = self._format_page_state(page_state)
        
        # Add visual context if available
        visual_hint = ""
        if visual_context:
            visual_hint = self._format_visual_context(visual_context)  # ← 新增
        

        # Construct user message with planning emphasis
        user_message = f"""=== USER GOAL ===
    {user_goal}

    === ACTION HISTORY ===
    {history_text}

    === CURRENT PAGE STATE ===
    {state_text}

    === VISUAL CONTEXT ===
    {visual_hint}

    === YOUR TASK ===
    Analyze the situation and provide:
    1. An overall plan to achieve the goal (or update existing plan based on history)
    2. Your current step number in that plan
    3. Detailed reasoning about what to do now
    4. The specific action to take"""

        print(f"\n{'='*60}")
        print(f"🎯 Goal: {user_goal}")
        print(f"📍 Current Page: {page_state['url']}")
        print(f"📋 Steps Taken: {len(action_history)}")
        print(f"{'='*60}")
        
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
                'overall_plan': output.overall_plan,
                'current_step': output.current_step,
                'thought': output.thought,
                'action': action_dict,
                'plan_adjustment': output.plan_adjustment
            }
            
            # Pretty print the plan
            self._print_decision(result)
            
            return result
            
        except Exception as e:
            print(f"❌ Planning failed: {e}")
            import traceback
            traceback.print_exc()
            
            return {
                'overall_plan': ["Error occurred", "Abort task"],
                'current_step': 0,
                'thought': f'Error occurred: {str(e)}',
                'action': {'type': 'done'},
                'plan_adjustment': None
            }
    
    def _format_history(self, action_history: List[Dict[str, Any]]) -> str:
        """Format action history for LLM"""
        if not action_history:
            return "No previous actions yet. This is the first step."
        
        lines = []
        for i, entry in enumerate(action_history, 1):
            action = entry['action']
            result = entry['result']
            thought = entry.get('thought', '')
            
            # Format action description
            action_desc = self._format_action_description(action)
            
            # Format result
            if result['success']:
                status = "✓ Success"
            else:
                status = f"✗ Failed: {result.get('error', 'Unknown error')}"
            
            lines.append(f"Step {i}: {action_desc} → {status}")
            
            if thought and len(thought) < 100:
                lines.append(f"         Reasoning: {thought}")
        
        return "\n".join(lines)
    
    def _format_action_description(self, action: Dict[str, Any]) -> str:
        """Format a single action for display"""
        action_type = action['type']
        
        if action_type == 'goto':
            return f"[Navigate to {action['url']}]"
        elif action_type == 'click':
            return f"[Click '{action['target']}']"
        elif action_type == 'type':
            text = action['text']
            target = action['target']
            # submit = action.get('submit', True)
            submit = action.get('submit', False)

            if submit:
                return f"[Type '{text}' into '{target}' and submit]"
            else:
                return f"[Type '{text}' into '{target}']"
        elif action_type == 'scroll':
            return f"[Scroll {action['direction']}]"
        elif action_type == 'done':
            return "[Task completed]"
        else:
            return f"[{action_type}]"
        
    
    def _print_decision(self, result: Dict[str, Any]):
        """Pretty print the planning decision"""
        
        print(f"\n📋 OVERALL PLAN:")
        for i, step in enumerate(result['overall_plan'], 1):
            current_marker = "👉 " if i == result['current_step'] else "   "
            print(f"{current_marker}{i}. {step}")
        
        if result.get('plan_adjustment'):
            print(f"\n🔄 PLAN ADJUSTMENT: {result['plan_adjustment']}")
        
        print(f"\n💭 Thought: {result['thought']}")
        
        action = result['action']
        print(f"\n🎯 Action: {action['type']}", end="")
        
        # Pretty print action details
        if action['type'] == 'goto':
            print(f" → {action['url']}")
        elif action['type'] == 'click':
            print(f" on '{action['target']}'")
        elif action['type'] == 'type':
            print(f" '{action['text']}' into '{action['target']}'", end="")
            if action.get('submit'):
                print(" (submit)")
            else:
                print()
        elif action['type'] == 'scroll':
            print(f" {action['direction']}")
        elif action['type'] == 'select':
            print(f" option '{action['option']}' from dropdown '{action['dropdown']}'")
        elif action['type'] == 'done':
            print(" ✅")
        else:
            print()
    
    def _format_page_state(self, page_state: Dict[str, Any]) -> str:
        """Format page state for LLM"""
        url = page_state.get('url', 'Unknown')
        title = page_state.get('title', 'Unknown')
        elements = page_state.get('interactive_elements', [])
        
        # Format elements list
        if not elements:
            elements_text = "  (No interactive elements found)"
        else:
            elements_text = "\n".join([
                f"  [{elem['role']}] name: '{elem['name']}'{f', value: \"{elem['value']}\"' if elem.get('value') else ''}"
                for elem in elements[:30]  # Limit to first 30
            ])
        
        footer = ""
        if len(elements) > 30:
            footer = f"\n  ... and {len(elements) - 30} more elements"
        
        return f"""URL: {url}
Title: {title}

Interactive Elements ({len(elements)} total):
{elements_text}{footer}"""
    
    def _format_visual_context(self, visual_context: Dict[str, Any]) -> str:
        """Format visual analysis context for LLM"""
        if not visual_context:
            return ""
        
        target = visual_context.get('target_element', {})
        page_ctx = visual_context.get('page_context', {})
        matched = visual_context.get('matched_element')
        
        lines = [
            "=== VISUAL ANALYSIS (FROM SCREENSHOT) ===",
            ""
        ]
        
        # Page context
        if page_ctx:
            lines.append(f"Page Type: {page_ctx.get('page_type', 'unknown')}")
            lines.append(f"Complexity: {page_ctx.get('complexity', 'unknown')}")
            lines.append("")
        
        # Target element
        if target:
            lines.append("Recommended Target Element:")
            lines.append(f"  Text: \"{target.get('primary_identifier', 'N/A')}\"")
            lines.append(f"  Type: {target.get('element_role', 'N/A')}")
            lines.append(f"  Prominence: {target.get('visual_prominence', 'N/A')}")
            lines.append(f"  Location: {target.get('location_hint', 'N/A')}")
            
            if target.get('description'):
                lines.append(f"  Why: {target['description']}")
            
            lines.append(f"  Confidence: {visual_context.get('confidence', 'N/A')}")
            lines.append("")
        
        # Matched element
        if matched:
            lines.append(f"✅ Vision-matched element in accessibility tree:")
            lines.append(f"   [{matched['role']}] name: '{matched['name']}'")
            lines.append("")
            lines.append("IMPORTANT: Strongly consider using this vision-identified element.")
        
        # Alternatives
        alternatives = visual_context.get('alternatives', [])
        if alternatives:
            lines.append("Alternative elements (if primary doesn't work):")
            for alt in alternatives[:2]:  # Limit to 2
                lines.append(f"  - \"{alt.get('primary_identifier', 'N/A')}\"")
            lines.append("")
        
        return "\n".join(lines)
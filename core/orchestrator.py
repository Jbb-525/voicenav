"""
Orchestrator: Manages the Observe-Think-Act loop for multi-step task execution
"""
from typing import Dict, Any, List
import asyncio
from core.executor import Executor
from core.planner import Planner


class Orchestrator:
    """
    Orchestrates multi-step web automation tasks using the OTA (Observe-Think-Act) loop
    """
    
    def __init__(self, executor: Executor, planner: Planner, use_vision: bool = False):
        """
        Initialize orchestrator
        
        Args:
            executor: Browser executor instance
            planner: LLM-based planner instance
            use_vision: Whether to use vision for element detection
        """
        self.executor = executor
        self.planner = planner
        self.use_vision = use_vision
        self.action_history: List[Dict[str, Any]] = []

    async def _wait_for_captcha_solve(
        self, 
        max_wait_seconds: int = 120,
        check_interval: int = 5
    ) -> bool:
        """
        Wait for CAPTCHA to be solved manually, polling periodically
        
        Args:
            max_wait_seconds: Maximum time to wait (default 2 minutes)
            check_interval: How often to check in seconds (default 5 seconds)
            
        Returns:
            True if CAPTCHA was solved, False if timeout
        """
        elapsed = 0
        checks = 0
        
        while elapsed < max_wait_seconds:
            # Wait before checking
            await asyncio.sleep(check_interval)
            elapsed += check_interval
            checks += 1
            
            # Get current page state
            try:
                current_state = await self.executor.get_page_state()
                
                # Check if still on CAPTCHA page
                if not self._is_captcha_page(current_state):
                    # CAPTCHA solved!
                    return True
                
                # Still on CAPTCHA, show progress
                remaining = max_wait_seconds - elapsed
                print(f"⏳ Still waiting... (check #{checks}, {remaining}s remaining)")
                
            except Exception as e:
                print(f"⚠️  Error checking page state: {e}")
                # Continue waiting even if error
        
        # Timeout reached
        return False
        
    async def run(
        self,
        user_goal: str,
        start_url: str = "https://www.google.com",
        max_steps: int = 10
    ) -> Dict[str, Any]:
        """
        Execute a multi-step task to achieve user's goal
        
        Args:
            user_goal: User's objective (e.g., "search for cats and click first result")
            start_url: Starting URL
            max_steps: Maximum number of steps to prevent infinite loops
            
        Returns:
            Execution summary with success status and history
        """
        print("\n" + "="*60)
        print("🚀 ORCHESTRATOR STARTING")
        print("="*60)
        print(f"Goal: {user_goal}")
        print(f"Start URL: {start_url}")
        print(f"Max Steps: {max_steps}")
        print("="*60)
        
        # Reset history
        self.action_history = []
        
        try:
            # 1. Start browser and navigate to initial page
            await self.executor.start(start_url)
            await asyncio.sleep(2)  # Let page load
            
            # 2. OTA Loop
            for step_num in range(1, max_steps + 1):
                print(f"\n{'='*60}")
                print(f"📍 STEP {step_num}/{max_steps}")
                print(f"{'='*60}")
                
                # === OBSERVE ===
                print("\n👀 OBSERVE: Getting current page state...")
                current_state = await self.executor.get_page_state()
                
                # Take screenshot for this step
                await self.executor.take_screenshot(f"step_{step_num:02d}_before.png")
                # === CHECK FOR CAPTCHA ===
                if self._is_captcha_page(current_state):
                    print(f"\n{'='*60}")
                    print("🤖 CAPTCHA DETECTED!")
                    print(f"{'='*60}")
                    print("A CAPTCHA verification is required to continue.")
                    print("Current URL:", current_state['url'])
                    print("\n⏳ Waiting for manual CAPTCHA solve...")
                    print("   Please solve the CAPTCHA in the browser window.")
                    print("   (Auto-detecting every 5 seconds, max wait: 120s)")
                    
                    # Take screenshot of CAPTCHA
                    await self.executor.take_screenshot(f"captcha_step_{step_num:02d}.png")
                    
                    # Auto-poll for CAPTCHA resolution
                    solved = await self._wait_for_captcha_solve(
                        max_wait_seconds=120,
                        check_interval=5
                    )
                    
                    if not solved:
                        print("\n❌ CAPTCHA not solved within timeout")
                        print("   Task cannot continue")
                        
                        return {
                            'success': False,
                            'error': 'CAPTCHA timeout - not solved within 120 seconds',
                            'steps_taken': step_num,
                            'history': self.action_history
                        }
                    
                    print("\n✅ CAPTCHA solved! Continuing task execution...")
                    await asyncio.sleep(2)
                    
                    # Get updated state after CAPTCHA solve
                    current_state = await self.executor.get_page_state()
                    await self.executor.take_screenshot(f"step_{step_num:02d}_captcha_solved.png")

                #=== CHECK FOR VISION ASSISTANCE ===
                visual_context = None

                if self.use_vision:
                    need_vision = self._should_use_vision(
                        current_state=current_state,
                        action_history=self.action_history,
                        step_num=step_num
                    )
                    
                    if need_vision:
                        print("\n🔍 VISION: Analyzing screenshot for guidance...")
                        visual_context = await self.executor.get_visual_analysis(
                            user_goal=user_goal,
                            current_state=current_state)

                # === THINK ===
                print("\n🤔 THINK: Planning next action...")
                decision = self.planner.decide(
                    user_goal=user_goal,
                    page_state=current_state,
                    action_history=self.action_history,
                    visual_context=visual_context
                )
                
                # === ACT ===
                print(f"\n⚡ ACT: Executing action...")
                result = await self.executor.execute_action(decision['action'])
                print(f"📊 Result: {result}")
                
                # Wait for page to settle after action
                await asyncio.sleep(2)
                
                # Take screenshot after action
                await self.executor.take_screenshot(f"step_{step_num:02d}_after.png")
                
                # === RECORD ===
                self.action_history.append({
                    'step': step_num,
                    'overall_plan': decision.get('overall_plan', []), 
                    'current_step': decision.get('current_step', 0),  
                    'action': decision['action'],
                    'thought': decision['thought'],
                    'result': result,
                    'plan_adjustment': decision.get('plan_adjustment')  
                })

                # # === RECORD ===
                # self.action_history.append({
                #     'step': step_num,
                #     'action': decision['action'],
                #     'thought': decision['thought'],
                #     'result': result
                # })
                
                # === CHECK COMPLETION ===
                if decision['action']['type'] == 'done':
                    print(f"\n{'='*60}")
                    print("✅ TASK COMPLETED!")
                    print(f"{'='*60}")
                    print(f"Total steps: {step_num}")
                    print(f"Final URL: {current_state['url']}")
                    
                    return {
                        'success': True,
                        'steps_taken': step_num,
                        'final_url': current_state['url'],
                        'history': self.action_history
                    }
                
                # === CHECK FOR REPEATED FAILURES ===
                if not result['success']:
                    # Count consecutive failures
                    consecutive_failures = 0
                    for entry in reversed(self.action_history):
                        if not entry['result']['success']:
                            consecutive_failures += 1
                        else:
                            break
                    
                    if consecutive_failures >= 3:
                        print(f"\n{'='*60}")
                        print("⚠️ TOO MANY CONSECUTIVE FAILURES")
                        print(f"{'='*60}")
                        print("Stopping to prevent infinite loop")
                        
                        return {
                            'success': False,
                            'error': 'Too many consecutive failures',
                            'steps_taken': step_num,
                            'history': self.action_history
                        }
            
            # Max steps reached
            print(f"\n{'='*60}")
            print("⚠️ MAX STEPS REACHED")
            print(f"{'='*60}")
            print(f"Task did not complete within {max_steps} steps")
            
            return {
                'success': False,
                'error': f'Max steps ({max_steps}) reached without completion',
                'steps_taken': max_steps,
                'history': self.action_history
            }
            
        except Exception as e:
            print(f"\n❌ ORCHESTRATOR ERROR: {e}")
            import traceback
            traceback.print_exc()
            
            return {
                'success': False,
                'error': str(e),
                'steps_taken': len(self.action_history),
                'history': self.action_history
            }
            
        finally:
            # Always close browser
            await asyncio.sleep(2)
            await self.executor.stop()
    
    def _is_captcha_page(self, page_state: Dict[str, Any]) -> bool:
        """
        Detect if current page is a CAPTCHA challenge
        
        Args:
            page_state: Current page state
            
        Returns:
            True if CAPTCHA detected
        """
        url = page_state.get('url', '').lower()
        title = page_state.get('title', '').lower()
        elements = page_state.get('interactive_elements', [])
        
        # Check for obvious CAPTCHA indicators
        captcha_keywords = ['captcha', 'unusual traffic', 'verify you are human', 'verify you\'re robot', 'are you a robot','prove you are human']
        
        # Check URL
        if any(keyword in url for keyword in captcha_keywords):
            print(f"Detected CAPTCHA keyword in URL: {url}")
            return True
        
        # Check title
        if any(keyword in title for keyword in captcha_keywords):
            print(f"Detected CAPTCHA keyword in title: {title}")
            return True
        
        # Check for suspiciously few interactive elements on Google
        if 'google' in url and len(elements) < 5:
            # Likely a CAPTCHA or error page
            # Normal Google pages have many interactive elements
            print(f"Detected low interactive elements on Google page: {len(elements)} elements")
            return True
        
        # Check element names for CAPTCHA text
        for elem in elements:
            elem_name = elem.get('name', '').lower()
            if any(keyword in elem_name for keyword in captcha_keywords):
                print(f"Detected CAPTCHA keyword in element name: {elem_name}")
                return True
        
        return False

    def _should_use_vision(
        self,
        current_state: Dict[str, Any],
        action_history: List[Dict[str, Any]],
        step_num: int
    ) -> bool:
        """
        Determine if vision assistance is needed
        
        Args:
            current_state: Current page state
            action_history: Previous actions
            step_num: Current step number
            
        Returns:
            True if vision should be used
        """
        # Strategy: Use vision when likely to help
        
        # # 1. Always use on first step (understand the page)
        # if step_num == 1:
        #     return True
        
        # 2. Use if many elements (hard to choose)
        num_elements = len(current_state.get('interactive_elements', []))
        if num_elements > 50:
            print(f"   📊 Many elements ({num_elements}) - using vision")
            return True
        
        # 3. Use if recent failures (need guidance)
        if action_history:
            recent_failures = 0
            for entry in action_history[-3:]:  # Last 3 actions
                if not entry['result'].get('success', False):
                    recent_failures += 1
            
            if recent_failures >= 2:
                print(f"   ⚠️  Multiple failures - using vision for guidance")
                return True
        
        # 4. Otherwise, skip vision (save cost)
        return False


    
    def _format_history(self, action_history: List[Dict[str, Any]]) -> str:
        """Format action history including plan information"""
        if not action_history:
            return "No previous actions yet. This is the first step."
        
        lines = []
        
        # Show the most recent plan
        if action_history:
            last_entry = action_history[-1]
            if 'overall_plan' in last_entry and last_entry['overall_plan']:
                lines.append("Last Plan:")
                for i, step in enumerate(last_entry['overall_plan'], 1):
                    marker = "✓" if i < last_entry.get('current_step', 0) else " "
                    lines.append(f"  [{marker}] {i}. {step}")
                lines.append("")
        
        # Show action history
        lines.append("Actions Taken:")
        for i, entry in enumerate(action_history, 1):
            action = entry['action']
            result = entry['result']
            
            # Format action description
            action_desc = self._format_action_description(action)
            
            # Format result
            if result['success']:
                status = "✓ Success"
            else:
                status = f"✗ Failed: {result.get('error', 'Unknown error')}"
            
            lines.append(f"Step {i}: {action_desc} → {status}")
        
        return "\n".join(lines)
    
    def print_summary(self, result: Dict[str, Any]):
        """Print a summary of the execution"""
        print(f"\n{'='*60}")
        print("📊 EXECUTION SUMMARY")
        print(f"{'='*60}")
        print(f"Success: {'✅ Yes' if result['success'] else '❌ No'}")
        print(f"Steps Taken: {result['steps_taken']}")
        
        if 'error' in result:
            print(f"Error: {result['error']}")
        
        if 'final_url' in result:
            print(f"Final URL: {result['final_url']}")
        
        print(f"\n{'='*60}")
        print("ACTION HISTORY:")
        print(f"{'='*60}")
        
        for entry in result['history']:
            step = entry['step']
            action = entry['action']
            result_status = entry['result']
            
            status_icon = "✓" if result_status['success'] else "✗"
            action_desc = self._format_action_brief(action)
            
            print(f"Step {step}: {status_icon} {action_desc}")
        
        print(f"{'='*60}\n")
    
    def _format_action_brief(self, action: Dict[str, Any]) -> str:
        """Format action for brief display"""
        action_type = action['type']
        
        if action_type == 'goto':
            return f"Navigate to {action['url']}"
        elif action_type == 'click':
            return f"Click '{action['target']}'"
        elif action_type == 'type':
            return f"Type '{action['text']}'"
        elif action_type == 'scroll':
            return f"Scroll {action['direction']}"
        elif action_type == 'select':
            return f"Select option '{action['option']}' from dropdown '{action['dropdown']}'"
        elif action_type == 'done':
            return "Task completed"
        else:
            return action_type
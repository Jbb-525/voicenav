"""
Orchestrator: Manages the Observe-Think-Act loop for multi-step task execution
"""
from typing import Dict, Any, List, Union
import asyncio
from core.executor import Executor
from core.planner import TextPlanner, VisionPlanner


class Orchestrator:
    """
    Orchestrates multi-step web automation tasks using the OTA (Observe-Think-Act) loop
    """
    
    def __init__(
        self, 
        executor: Executor, 
        planner: Union[TextPlanner, VisionPlanner]
    ):
        """
        Initialize orchestrator
        
        Args:
            executor: Browser executor instance
            planner: TextPlanner or VisionPlanner instance
        """
        self.executor = executor
        self.planner = planner
        self.action_history: List[Dict[str, Any]] = []
    
    async def run(
        self,
        user_goal: str,
        start_url: str = "https://www.google.com",
        max_steps: int = 10
    ) -> Dict[str, Any]:
        """
        Execute a multi-step task to achieve user's goal
        
        Args:
            user_goal: User's objective
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
        planner_type = "VisionPlanner" if isinstance(self.planner, VisionPlanner) else "TextPlanner"
        print(f"Planner: {planner_type}")
        print("="*60)
        
        # Reset history
        self.action_history = []
        
        try:
            # Start browser and navigate
            await self.executor.start(start_url)
            await asyncio.sleep(2)
            
            # OTA Loop
            for step_num in range(1, max_steps + 1):
                print(f"\n{'='*60}")
                print(f"📍 STEP {step_num}/{max_steps}")
                print(f"{'='*60}")
                
                # === OBSERVE ===
                print("\n👀 OBSERVE: Getting current page state...")
                current_state = await self.executor.get_page_state()
                
                print(f"\n📊 Page State:")
                print(f"   URL: {current_state['url']}")
                print(f"   Title: {current_state['title']}")
                print(f"   Interactive Elements: {len(current_state.get('interactive_elements', []))}")
                
                await self.executor.take_screenshot(f"step_{step_num:02d}_before.png")
                
                # === CHECK FOR CAPTCHA ===
                if self._is_captcha_page(current_state):
                    solved = await self._handle_captcha(current_state, step_num)
                    if not solved:
                        return {
                            'success': False,
                            'error': 'CAPTCHA timeout',
                            'steps_taken': step_num,
                            'history': self.action_history
                        }
                    
                    # Get updated state after CAPTCHA
                    current_state = await self.executor.get_page_state()
                    await self.executor.take_screenshot(f"step_{step_num:02d}_captcha_solved.png")
                
                # === THINK ===
                print("\n🤔 THINK: Planning next action...")
                
                if isinstance(self.planner, VisionPlanner):
                    # VisionPlanner needs screenshot
                    screenshot = await self.executor.get_screenshot_base64()
                    decision = self.planner.decide(
                        user_goal=user_goal,
                        page_state=current_state,
                        action_history=self.action_history,
                        screenshot_base64=screenshot
                    )
                else:
                    # TextPlanner uses only AXTree
                    decision = self.planner.decide(
                        user_goal=user_goal,
                        page_state=current_state,
                        action_history=self.action_history
                    )
                
                # === ACT ===
                print(f"\n⚡ ACT: Executing action...")
                result = await self.executor.execute_action(decision['action'])
                print(f"📊 Result: {result}")
                
                await asyncio.sleep(2)
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
                    # Count consecutive failures from the end
                    consecutive_failures = 0
                    for entry in reversed(self.action_history):
                        if not entry['result']['success']:
                            consecutive_failures += 1
                        else:
                            break  # Stop at first success
                    
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
            
            return {
                'success': False,
                'error': f'Max steps ({max_steps}) reached',
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
            await asyncio.sleep(2)
            await self.executor.stop()
    
    async def _handle_captcha(
        self, 
        page_state: Dict[str, Any],
        step_num: int
    ) -> bool:
        """Handle CAPTCHA detection and manual solving"""
        print(f"\n{'='*60}")
        print("🤖 CAPTCHA DETECTED!")
        print(f"{'='*60}")
        print(f"Current URL: {page_state['url']}")
        print("\n⏳ Waiting for manual CAPTCHA solve...")
        print("   Please solve the CAPTCHA in the browser window.")
        print("   (Auto-detecting every 5 seconds, max wait: 120s)")
        
        await self.executor.take_screenshot(f"captcha_step_{step_num:02d}.png")
        
        # Wait for CAPTCHA to be solved
        max_wait = 120
        check_interval = 5
        elapsed = 0
        
        while elapsed < max_wait:
            await asyncio.sleep(check_interval)
            elapsed += check_interval
            
            try:
                current_state = await self.executor.get_page_state()
                
                if not self._is_captcha_page(current_state):
                    print("\n✅ CAPTCHA solved! Continuing...")
                    return True
                
                remaining = max_wait - elapsed
                print(f"⏳ Still waiting... ({remaining}s remaining)")
                
            except Exception as e:
                print(f"⚠️  Error checking: {e}")
        
        print("\n❌ CAPTCHA not solved within timeout")
        return False
    
    def _is_captcha_page(self, page_state: Dict[str, Any]) -> bool:
        """Detect if current page is a CAPTCHA challenge"""
        url = page_state.get('url', '').lower()
        title = page_state.get('title', '').lower()
        elements = page_state.get('interactive_elements', [])
        
        captcha_keywords = [
            'captcha', 'unusual traffic', 'verify you are human',
            'verify you\'re robot', 'are you a robot', 'prove you are human'
        ]
        
        # Check URL
        if any(keyword in url for keyword in captcha_keywords):
            return True
        
        # Check title
        if any(keyword in title for keyword in captcha_keywords):
            return True
        
        # Check for suspiciously few elements on Google
        if 'google' in url and len(elements) < 5:
            return True
        
        return False
    
    def print_summary(self, result: Dict[str, Any]):
        """Print execution summary"""
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
            return f"Select '{action['option']}' from '{action['dropdown']}'"
        elif action_type == 'done':
            return "Task completed"
        else:
            return action_type
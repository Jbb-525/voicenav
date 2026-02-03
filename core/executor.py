"""
Executor: Handles browser operations and page state extraction
"""
from playwright.async_api import async_playwright, Page, Browser
import json
from typing import Dict, Any, Optional
import asyncio


class Executor:
    """Browser executor for web automation"""
    
    def __init__(self, headless: bool = False):
        """
        Initialize executor
        
        Args:
            headless: Whether to run browser in headless mode
        """
        self.headless = headless
        self.browser: Optional[Browser] = None
        self.page: Optional[Page] = None
        self.playwright = None
        
    async def start(self, start_url: str = "https://www.google.com"):
        """
        Launch browser
        
        Args:
            start_url: Initial page URL
        """
        print(f"🚀 Launching browser, navigating to: {start_url}")
        
        # Start Playwright
        self.playwright = await async_playwright().start()
        
        # Launch Chromium browser
        self.browser = await self.playwright.chromium.launch(
            headless=self.headless,
            slow_mo=500  # Delay 500ms per action for observation
        )
        
        # Create new page
        self.page = await self.browser.new_page()
        
        # Set viewport size
        await self.page.set_viewport_size({"width": 1280, "height": 720})
        
        # Navigate to start URL
        await self.page.goto(start_url)
        
        print("✅ Browser launched successfully")
        
    async def stop(self):
        """Close browser"""
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()
        print("🛑 Browser closed")
    
    async def get_page_state(self) -> Dict[str, Any]:
        """
        Get current page state using Accessibility Tree
        
        Returns:
            Dictionary containing URL, title, and accessibility tree
        """
        if not self.page:
            raise RuntimeError("Browser not started. Call start() first.")
        
        # Get basic info
        url = self.page.url
        title = await self.page.title()
        
        # Get Accessibility Tree
        acc_tree = await self.page.accessibility.snapshot()
        
        # Extract interactive elements
        interactive_elements = self._extract_interactive_elements(acc_tree)
        
        state = {
            'url': url,
            'title': title,
            'interactive_elements': interactive_elements,
            'raw_tree': acc_tree  # Keep raw tree for debugging
        }
        
        print(f"\n📊 Page State:")
        print(f"   URL: {url}")
        print(f"   Title: {title}")
        print(f"   Interactive Elements: {len(interactive_elements)}")
        
        return state
    
    def _extract_interactive_elements(self, node: Dict, elements: list = None, path: str = "") -> list:
        """
        Extract interactive elements from Accessibility Tree
        
        Args:
            node: Current node
            elements: Accumulated element list
            path: Node path
            
        Returns:
            List of interactive elements
        """
        if elements is None:
            elements = []
        
        # Interactive role types
        interactive_roles = {
            'button', 'link', 'textbox', 'searchbox', 
            'combobox', 'checkbox', 'radio', 'menuitem',
            'tab', 'option', 'switch'
        }
        
        # If current node is interactive
        if node and node.get('role') in interactive_roles:
            element = {
                'role': node['role'],
                'name': node.get('name', ''),
                'value': node.get('value', ''),
                'path': path
            }
            elements.append(element)
        
        # Recursively process children
        children = node.get('children', []) if node else []
        for i, child in enumerate(children):
            child_path = f"{path}/{i}" if path else str(i)
            self._extract_interactive_elements(child, elements, child_path)
        
        return elements
    
    async def execute_action(self, action: Dict[str, Any]) -> Dict[str, Any]:
        """Execute an action"""
        if not self.page:
            raise RuntimeError("Browser not started")
        
        action_type = action.get('type')
        
        print(f"\n⚡ Executing Action: {action_type}")
        print(f"   Details: {action}")
        
        try:
            if action_type == 'goto':
                result = await self._action_goto({'url': action.get('url')})
            elif action_type == 'click':
                result = await self._action_click({'target': action.get('target')})
            elif action_type == 'type':
                result = await self._action_type({
                    'target': action.get('target'),
                    'text': action.get('text'),
                    'submit': action.get('submit', False)
                })
            elif action_type == 'scroll':
                result = await self._action_scroll({'direction': action.get('direction')})
            elif action_type == 'done':
                result = await self._action_done({})
            else:
                result = {'success': False, 'error': f'Unknown action: {action_type}'}
            
            return result
        
        except Exception as e:
            print(f"❌ Action failed: {e}")
            return {'success': False, 'error': str(e)}
    
    
    async def _action_goto(self, params: Dict) -> Dict:
        """Navigate to URL"""
        url = params.get('url')
        if not url:
            return {'success': False, 'error': 'Missing url parameter'}
        
        await self.page.goto(url)
        await self.page.wait_for_load_state('networkidle')
        
        print(f"✅ Navigated to: {url}")
        return {'success': True, 'message': f'Navigated to {url}'}
    
    async def _action_click(self, params: Dict) -> Dict:
        """Click element"""
        target = params.get('target')
        if not target:
            return {'success': False, 'error': 'Missing target parameter'}
        
        # Try to find element by text
        # Support multiple selectors
        selectors = ['button','link']
        
        clicked = False
        for selector in selectors:
            try:
                element = self.page.get_by_role(selector, name=target)
                if await element.count() > 0:
                    await element.click()
                    clicked = True
                    print(f"✅ Clicked: {target}")
                    break
            except:
                continue
        
        if not clicked:
            return {'success': False, 'error': f'Element not found: {target}'}
        
        # Wait for page to stabilize
        await self.page.wait_for_load_state('networkidle', timeout=3000)
        
        return {'success': True, 'message': f'Clicked {target}'}
    
    async def _action_type(self, params: Dict) -> Dict:
        """Type text into input"""
        target = params.get('target')
        text = params.get('text')
        submit = params.get('submit', False)
        
        if not target or not text:
            return {'success': False, 'error': 'Missing target or text parameter'}
        
        # Find input field
        selectors = [
            f'combobox',
            f'textbox',
            f'searchbox'
        ]
        
        typed = False
        for selector in selectors:
            try:
                element = self.page.get_by_role(selector, name=target)

                if await element.count() > 0:
                    # await element.click()
                    await element.fill(text)
                    typed = True
                    if submit:
                        await element.press('Enter')
                        print(f"✅ Typed '{text}' into '{target}' and submitted")
                    else:
                        print(f"✅ Typed: {text} into {target}")
                    break
            except:
                continue
        
        if not typed:
            return {'success': False, 'error': f'Input field not found: {target}'}
        
        return {'success': True, 'message': f'Typed {text}'}
    
    async def _action_scroll(self, params: Dict) -> Dict:
        """Scroll page"""
        direction = params.get('direction', 'down')
        
        if direction == 'down':
            await self.page.evaluate('window.scrollBy(0, 500)')
        elif direction == 'up':
            await self.page.evaluate('window.scrollBy(0, -500)')
        else:
            return {'success': False, 'error': f'Unknown scroll direction: {direction}'}
        
        print(f"✅ Scrolled {direction}")
        return {'success': True, 'message': f'Scrolled {direction}'}
    
    async def take_screenshot(self, path: str = "screenshot.png"):
        """Take screenshot"""
        if self.page:
            # Ensure screenshots directory exists
            from pathlib import Path
            screenshot_dir = Path("screenshots")
            screenshot_dir.mkdir(exist_ok=True)
            
            # Save to screenshots folder
            full_path = screenshot_dir / path
            await self.page.screenshot(path=str(full_path))
            print(f"📸 Screenshot saved: {full_path}")

    async def _action_done(self, params: Dict) -> Dict:
        """Task completion action"""
        print("✅ Task marked as done")
        return {'success': True, 'message': 'Task completed'}

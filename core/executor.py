"""
Executor: Handles browser operations and page state extraction
"""
from numpy import rint
from playwright.async_api import async_playwright, Page, Browser, Playwright
from playwright_stealth import Stealth
import json
import time
from typing import Dict, Any, Optional
import asyncio


class Executor:
    """Browser executor for web automation"""

    def __init__(
        self,
        headless: bool = False,
        use_vision: bool = False,
        frame_queue: Optional[asyncio.Queue] = None,
    ):
        """
        Initialize executor

        Args:
            headless: Whether to run browser in headless mode
            frame_queue: Optional queue to receive base64 JPEG frames from CDP screencast
        """
        self.headless = headless
        self.use_vision = use_vision
        self.browser: Optional[Browser] = None
        self.page: Optional[Page] = None
        self.playwright: Optional[Playwright] = None
        self.stealth_context = None
        self._cdp_session = None
        self._frame_queue: Optional[asyncio.Queue] = frame_queue
        self._last_frame_time: float = 0
        self._frame_interval: float = 0.1  # 10fps max

        # # Initialize vision analyzer if enabled
        # if self.use_vision:
        #     from core.vision import VisionAnalyzer
        #     self.vision = VisionAnalyzer()
        #     print("🔍 Vision mode enabled")
        # else:
        #     self.vision = None
        
    async def start(self, start_url: str = "https://www.google.com"):
        """
        Launch browser
        
        Args:
            start_url: Initial page URL
        """
        print(f"🚀 Launching browser, navigating to: {start_url}")
        
        # Start Playwright
        self.stealth_context = Stealth().use_async(async_playwright())
        self.playwright = await self.stealth_context.__aenter__()
        # self.playwright = await async_playwright().start()
        
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

        # Auto-start screencast if a frame_queue was provided
        if self._frame_queue is not None:
            await self.start_screencast(self._frame_queue)

        print("✅ Browser launched successfully")
        
    async def stop(self):
        """Close browser"""
        await self.stop_screencast()
        if self.browser:
            await self.browser.close()

        # Properly exit stealth context
        if self.stealth_context:
            await self.stealth_context.__aexit__(None, None, None)

        print("🛑 Browser closed")

    async def start_screencast(self, frame_queue: asyncio.Queue):
        """Start CDP screencast and push base64 JPEG frames to frame_queue."""
        if not self.page:
            return
        self._frame_queue = frame_queue
        self._cdp_session = await self.page.context.new_cdp_session(self.page)
        await self._cdp_session.send("Page.startScreencast", {
            "format": "jpeg",
            "quality": 70,
            "maxWidth": 1280,
            "maxHeight": 720,
            "everyNthFrame": 1,
        })
        self._cdp_session.on("Page.screencastFrame", self._on_screencast_frame)
        print("📹 Screencast started")

    def _on_screencast_frame(self, params: Dict):
        """Handle incoming screencast frame (sync callback, schedules async work)."""
        now = time.monotonic()
        if now - self._last_frame_time < self._frame_interval:
            # Throttle: ack but discard the frame
            asyncio.ensure_future(
                self._cdp_session.send("Page.screencastFrameAck", {"sessionId": params["sessionId"]})
            )
            return
        self._last_frame_time = now
        frame_data = params["data"]
        session_id = params["sessionId"]
        if self._frame_queue is not None:
            asyncio.ensure_future(self._frame_queue.put(frame_data))
        asyncio.ensure_future(
            self._cdp_session.send("Page.screencastFrameAck", {"sessionId": session_id})
        )

    async def stop_screencast(self, clear_queue: bool = True):
        """Stop CDP screencast. Pass clear_queue=False when re-attaching to a new page."""
        if self._cdp_session:
            try:
                await self._cdp_session.send("Page.stopScreencast")
            except Exception:
                pass
            self._cdp_session = None
        if clear_queue:
            self._frame_queue = None

    async def dispatch_reload(self):
        """Reload the current page."""
        if self.page:
            await self.page.reload()

    async def dispatch_click(self, x: int, y: int):
        """Forward a click to the browser via CDP (used for web UI interaction)."""
        if not self._cdp_session:
            return
        base = {"x": x, "y": y, "button": "left", "clickCount": 1, "pointerType": "mouse"}
        await self._cdp_session.send("Input.dispatchMouseEvent", {**base, "type": "mousePressed", "buttons": 1})
        await self._cdp_session.send("Input.dispatchMouseEvent", {**base, "type": "mouseReleased", "buttons": 0})

    async def dispatch_key(self, text: str):
        """Forward a text character to the browser via CDP."""
        if not self._cdp_session:
            return
        for char in text:
            await self._cdp_session.send("Input.dispatchKeyEvent", {"type": "char", "text": char})
    
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
            elif action_type == 'select':
                result = await self._action_select(action)
            elif action_type == 'done':
                result = await self._action_done({})
            else:
                result = {'success': False, 'error': f'Unknown action: {action_type}'}
            
            return result
        
        except Exception as e:
            print(f"❌ Action failed: {e}")
            return {'success': False, 'error': str(e)}
    

    async def _wait_after_click(self):
        """
        Smart wait after clicking to ensure page stability
        Uses multiple strategies to determine when page is ready
        """
        try:
            # Strategy 1: Wait for DOM to be ready (fast, reliable)
            await self.page.wait_for_load_state('domcontentloaded', timeout=5000)
            print("   DOM loaded")
        except Exception as e:
            print(f"   DOM load timeout (continuing anyway): {e}")
        
        # Strategy 2: Give page a moment to settle
        await asyncio.sleep(1.5)
        
        # Strategy 3: Optionally wait for network to be quieter (but don't block on it)
        try:
            await self.page.wait_for_load_state('networkidle', timeout=2000)
            print("   Network idle")
        except:
            # Network still active, but that's okay for many modern sites
            print("   Network still active (normal for dynamic sites)")
            pass

    async def _click_and_handle_new_tab(self, element, target: str) -> bool:
        try:
            new_page_future = asyncio.get_event_loop().create_future()
            
            def on_popup(p):
                if not new_page_future.done():
                    new_page_future.set_result(p)
            
            self.page.context.on('page', on_popup)

            await element.click(no_wait_after=True)
            print(f"✅ Clicked: {target}")

            try:
                new_page = await asyncio.wait_for(new_page_future, timeout=1.0)

                print(f"   ↗️  New tab detected, switching...")
                await new_page.wait_for_load_state('domcontentloaded', timeout=5000)
                self.page = new_page
                print(f"   📍 Now on: {self.page.url}")

                # Re-attach screencast to the new page (keep frame_queue alive)
                if self._frame_queue is not None:
                    fq = self._frame_queue
                    await self.stop_screencast(clear_queue=False)
                    await self.start_screencast(fq)

            except asyncio.TimeoutError:
                print(f"   📍 Same page navigation")
            finally:
                self.page.context.remove_listener('page', on_popup)

            await self._wait_after_click()
            return True

        except Exception as e:
            print(f"   ❌ Click error: {e}")
            return False

    async def _wait_after_submit(self):
        """
        Wait after submitting a form (e.g., search)
        Usually involves navigation, so wait longer
        """
        try:
            # Wait for navigation to complete
            await self.page.wait_for_load_state('domcontentloaded', timeout=8000)
            print("   Page loaded after submit")
        except Exception as e:
            print(f"   Submit navigation timeout: {e}")
        
        # Let page settle
        await asyncio.sleep(2)
        
        # Try to wait for network idle (but don't block)
        try:
            await self.page.wait_for_load_state('networkidle', timeout=3000)
            print("   Network settled")
        except:
            print("   Network still active")
            pass


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
        selectors = ['button', 'link', 'menuitemradio', 'menuitem', 'option']
        
        clicked = False
        for selector in selectors:
            try:
                element = self.page.get_by_role(selector, name=target).first
                if await element.count() > 0:
                    clicked = await self._click_and_handle_new_tab(element, target)
                    if clicked:
                        print(f"✅ Clicked: {target}")
                    break
            except:
                continue

        if not clicked:
            try:
                element = self.page.get_by_text(target, exact=True).first
                if await element.count() > 0:
                    clicked = await self._click_and_handle_new_tab(element, target)
                    if clicked:
                        print(f"✅ Clicked via get_by_text: {target}")
            except:
                pass

        if not clicked:
            try:
                element = self.page.get_by_text(target, exact=False).first
                if await element.count() > 0:
                    clicked = await self._click_and_handle_new_tab(element, target)
                    if clicked:
                        print(f"✅ Clicked via get_by_text fuzzy: {target}")
            except:
                pass

        if not clicked:
            return {'success': False, 'error': f'Element not found: {target}'}
        
        # Wait for page to stabilize
        # await self.page.wait_for_load_state('networkidle', timeout=5000)
        # await self._wait_after_click()

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
                element = self.page.get_by_role(selector, name=target).first

                if await element.count() > 0:
                    # await element.click()
                    await element.fill(text)
                    typed = True
                    if submit:
                        await element.press('Enter')
                        print(f"✅ Typed '{text}' into '{target}' and submitted")
                        await self._wait_after_submit() 
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

    async def get_screenshot_base64(self) -> str:
        """
        Get current page screenshot as base64 string
        
        Returns:
            Base64 encoded PNG screenshot
        """
        try:
            screenshot_bytes = await self.page.screenshot(type='png')
            import base64
            screenshot_base64 = base64.b64encode(screenshot_bytes).decode('utf-8')
            return screenshot_base64
        except Exception as e:
            print(f"❌ Screenshot capture failed: {e}")
            return ""
    
    async def _action_select(self, params: Dict) -> Dict:
        """Select option from dropdown/combobox"""
        dropdown = params.get('dropdown')
        option = params.get('option')
        
        if not dropdown or not option:
            return {'success': False, 'error': 'Missing dropdown or option parameter'}
        
        async def find_option() -> any:
            """Try all strategies to find the option element"""
            finders = [
                lambda: self.page.get_by_role("option", name=option).first,
                lambda: self.page.get_by_role("menuitemradio", name=option).first,
                lambda: self.page.get_by_role("menuitem", name=option).first,
                lambda: self.page.locator(f'[role="option"]:has-text("{option}")').first,
                lambda: self.page.locator(f'li:has-text("{option}")').first,
                lambda: self.page.get_by_text(option, exact=True).first,
            ]
            for finder in finders:
                try:
                    el = finder()
                    if await el.count() > 0:
                        return el
                except:
                    continue
            return None

        try:
            print(f"\n⚡ Executing Action: select")
            print(f"   Details: {params}")

            # ── Step 1: check if dropdown is already open ────────────
            option_element = await find_option()
            if option_element:
                print(f"   ✓ Dropdown already open, found option directly")
                await option_element.click(timeout=5000)
                await asyncio.sleep(1)
                print(f"✅ Selected '{option}' from '{dropdown}'")
                return {'success': True, 'message': f'Selected {option} from {dropdown}'}

            # ── Step 2: find the combobox ────────────────────────────
            combobox = None
            for role, name in [('combobox', dropdown), ('listbox', dropdown), ('button', dropdown)]:
                try:
                    el = self.page.get_by_role(role, name=name).first
                    if await el.count() > 0:
                        combobox = el
                        print(f"   ✓ Found dropdown: [{role}] {name}")
                        break
                except:
                    continue

            if not combobox:
                return {'success': False, 'error': f'Dropdown not found: {dropdown}'}

            # ── Step 3: native <select> ──────────────────────────────
            tag_name = await combobox.evaluate('el => el.tagName.toLowerCase()')

            if tag_name == 'select':
                print(f"   ℹ️  Native <select> detected")
                try:
                    await combobox.scroll_into_view_if_needed(timeout=3000)
                except:
                    pass

                selected = False
                for method, kwargs in [
                    ('label', {'label': option}),
                    ('value', {'value': option}),
                ]:
                    if selected:
                        break
                    try:
                        await combobox.select_option(**kwargs, timeout=5000)
                        selected = True
                        print(f"   ✓ Selected by {method}: {option}")
                    except:
                        pass

                # fallback: match by text across all <option> elements
                if not selected:
                    try:
                        for idx, opt in enumerate(await combobox.locator('option').all()):
                            text = await opt.text_content()
                            if option.lower() in text.lower():
                                await combobox.select_option(index=idx, timeout=5000)
                                selected = True
                                print(f"   ✓ Selected by index {idx}: {text}")
                                break
                    except:
                        pass

                if not selected:
                    return {'success': False, 'error': f'Could not select option: {option}'}

                await asyncio.sleep(1.5)
                print(f"✅ Selected '{option}' from '{dropdown}'")
                return {'success': True, 'message': f'Selected {option} from {dropdown}'}

            # ── Step 4: custom dropdown — open then find ─────────────
            print(f"   ℹ️  Custom dropdown (tag: {tag_name})")
            try:
                await combobox.scroll_into_view_if_needed(timeout=3000)
            except:
                pass

            await combobox.click(timeout=5000)
            print(f"   ✓ Opened dropdown")
            await asyncio.sleep(0.5)

            option_element = await find_option()
            if not option_element:
                return {'success': False, 'error': f'Option not found: {option}'}

            await option_element.click(timeout=5000)
            print(f"   ✓ Selected option: {option}")
            await asyncio.sleep(1)
            print(f"✅ Selected '{option}' from '{dropdown}'")
            return {'success': True, 'message': f'Selected {option} from {dropdown}'}

        except Exception as e:
            print(f"   ❌ Select failed: {e}")
            return {'success': False, 'error': f'Select failed: {str(e)}'}


    async def _action_done(self, params: Dict) -> Dict:
        """Task completion action"""
        print("✅ Task marked as done")
        return {'success': True, 'message': 'Task completed'}


"""
Test stealth mode
"""
import asyncio
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from core.executor import Executor


async def test_stealth():
    """Test if stealth mode is working"""
    
    executor = Executor(headless=False)
    
    try:
        await executor.start("https://bot.sannysoft.com/")
        
        print("\n" + "="*60)
        print("Testing stealth mode...")
        print("="*60)
        
        # Wait for page to load
        await asyncio.sleep(3)
        
        # Check navigator.webdriver
        webdriver_status = await executor.page.evaluate("navigator.webdriver")
        print(f"\nnavigator.webdriver: {webdriver_status}")
        print("(Should be undefined or false for good stealth)")
        
        # Take screenshot
        await executor.take_screenshot("stealth_test.png")
        
        print("\n✅ Check the browser window and screenshot.")
        print("   Green checks = good stealth")
        print("   Red X's = bot detected")
        
        await asyncio.sleep(10)  # Wait to observe
        
    finally:
        await executor.stop()


if __name__ == "__main__":
    asyncio.run(test_stealth())
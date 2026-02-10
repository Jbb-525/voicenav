"""
Test planner with executor integration
"""
import asyncio
import sys
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from core.executor import Executor
from core.planner import Planner


async def test_planner():
    """Test Planner + Executor integration"""
    
    # Initialize
    executor = Executor(headless=False)
    planner = Planner(model="gpt-4o-mini")
    
    try:
        print("\n" + "="*60)
        print("PLANNER + EXECUTOR INTEGRATION TEST")
        print("="*60)
        
        # 1. Start browser
        await executor.start("https://www.google.com")
        await asyncio.sleep(2)
        
        # 2. Get initial page state
        state = await executor.get_page_state()
        await executor.take_screenshot("01_initial_state.png")

        # 3. Test Case 1: Search query
        print("\n" + "="*60)
        print("TEST CASE 1: Search for 'Python tutorials'")
        print("="*60)
        
        user_input = "search for Python tutorials"
        decision = planner.decide(user_input, state)
        
        # Execute the planned action
        result = await executor.execute_action(decision['action'])
        print(f"\n📊 Execution Result: {result}")
        
        await asyncio.sleep(3)
        await executor.take_screenshot("02_after_search.png")
        
        # # 4. Get new state
        # new_state = await executor.get_page_state()
        # print(f"\n📍 New URL: {new_state['url']}")
        # print(f"📄 New Title: {new_state['title']}")
        
        # # 5. Test Case 2: Navigate to a specific URL
        # print("\n" + "="*60)
        # print("TEST CASE 2: Go to GitHub")
        # print("="*60)
        
        # user_input_2 = "go to github"
        # decision_2 = planner.decide(user_input_2, new_state)
        
        # result_2 = await executor.execute_action(decision_2['action'])
        # print(f"\n📊 Execution Result: {result_2}")
        
        # await asyncio.sleep(3)
        # await executor.take_screenshot("03_github.png")
        
        # print("\n" + "="*60)
        # print("✅ ALL TESTS COMPLETED")
        # print("="*60)
        
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        
    finally:
        await asyncio.sleep(2)
        await executor.stop()


if __name__ == "__main__":
    asyncio.run(test_planner())
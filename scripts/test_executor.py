# """
# Get interactive elements from a page and print them all out
# """
# import asyncio
# import sys
# from pathlib import Path

# # Add project root to Python path
# project_root = Path(__file__).parent.parent
# sys.path.insert(0, str(project_root))

# from core.executor import Executor


# async def test_executor():
#     """Test basic Executor operations"""
    
#     # Create executor
#     executor = Executor(headless=False)
    
#     try:
#         # 1. Launch browser
#         await executor.start("https://www.google.com")
#         await asyncio.sleep(2)
        
#         # 2. Get page state
#         state = await executor.get_page_state()
        
#         # Print ALL interactive elements to see what's available
#         print("\n=== ALL Interactive Elements ===")
#         for i, elem in enumerate(state['interactive_elements']):
#             print(f"{i+1}. [{elem['role']}] name: '{elem['name']}' | value: '{elem['value']}'")
        
#         print("\n" + "="*50)
#         print("Check the elements above to find the correct names")
#         print("="*50)
        
#         # Wait so you can see the browser
#         await asyncio.sleep(5)
        
#         # Take screenshot before closing
#         await executor.take_screenshot("google_homepage.png")
        
#     finally:
#         # Close browser
#         await executor.stop()


# if __name__ == "__main__":
#     asyncio.run(test_executor())



"""
Test executor functionality
"""
import asyncio
from core.executor import Executor

async def test_executor():
    """Test basic Executor operations"""
    
    # Create executor
    executor = Executor(headless=False)
    
    try:
        # 1. Launch browser
        await executor.start("https://www.google.com")
        await asyncio.sleep(2)
        
        # 2. Get page state
        state = await executor.get_page_state()
        
        # Print first 5 interactive elements
        print("\nFirst 5 interactive elements:")
        for i, elem in enumerate(state['interactive_elements'][:5]):
            print(f"  {i+1}. {elem['role']}: {elem['name']}")
        
        # 3. Test typing
        print("\nTest: Type into search box")
        result = await executor.execute_action({
            'type': 'type',
            'params': {
                'target': 'Search',
                'text': 'Playwright tutorial'
            }
        })
        print(f"Result: {result}")
        await asyncio.sleep(2)
        
        # 4. Test clicking
        print("\nTest: Click search button")
        result = await executor.execute_action({
            'type': 'click',
            'params': {
                'target': 'Google Search'
            }
        })
        print(f"Result: {result}")
        await asyncio.sleep(3)
        
        # 5. Take screenshot
        await executor.take_screenshot("test_result.png")
        
        # 6. Get new page state
        new_state = await executor.get_page_state()
        print(f"\nNew page URL: {new_state['url']}")
        
    finally:
        # Close browser
        await executor.stop()


if __name__ == "__main__":
    asyncio.run(test_executor())



"""
Test Orchestrator with multi-step tasks
"""
import asyncio
import sys
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from core.executor import Executor
from core.planner import Planner
from core.orchestrator import Orchestrator


async def test_simple_task():
    """Test simple task"""
    executor = Executor(headless=False)
    planner = Planner(model="gpt-4o")
    orchestrator = Orchestrator(executor, planner)
    
    print("\n📝 Test: Simple navigation task")
    
    result = await orchestrator.run(
        user_goal="go to Github",
        start_url="https://www.google.com",
        max_steps=5
    )
    
    orchestrator.print_summary(result)


async def test_search_task():
    """Test search and click task"""
    executor = Executor(headless=False)
    planner = Planner(model="gpt-4o")
    orchestrator = Orchestrator(executor, planner)
    
    print("\n📝 Test: Search and click first result")
    
    result = await orchestrator.run(
        user_goal="search for RLHF tech report from openai",
        start_url="https://www.google.com",
        max_steps=6
    )
    
    orchestrator.print_summary(result)


async def test_complex_task():
    """Test complex e-commerce task"""
    executor = Executor(headless=False)
    planner = Planner(model="gpt-4o")
    orchestrator = Orchestrator(executor, planner)
    
    print("\n📝 Test: Find cheapest product on Amazon")
    
    result = await orchestrator.run(
        user_goal="find the cheapest toothbrush on Amazon",
        start_url="https://www.google.com",
        max_steps=10  # More steps for complex task
    )
    
    orchestrator.print_summary(result)

async def test_with_vision():
    """Test complex task with vision assistance"""
    executor = Executor(headless=False, use_vision=True)
    planner = Planner(model="gpt-4o")
    orchestrator = Orchestrator(executor, planner, use_vision=True)
    
    print("\n" + "="*60)
    print("TESTING WITH VISION ASSISTANCE")
    print("="*60)
    
    print("\n📝 Test: Find cheapest product on Amazon")
    
    result = await orchestrator.run(
        user_goal="find the cheapest toothbrush on Amazon",
        start_url="https://www.google.com",
        max_steps=10  # More steps for complex task
    )
    
    orchestrator.print_summary(result)


async def test_direct_navigation():
    """Test 5: Direct URL navigation + scroll to find content
    Tests: goto action, scroll action, multi-step reading task
    """
    executor = Executor(headless=False)
    planner = Planner(model="gpt-4o")
    orchestrator = Orchestrator(executor, planner)

    print("\n📝 Test: Direct navigation to Wikipedia and find info")

    result = await orchestrator.run(
        user_goal="go to the Wikipedia page for Large Language Model",
        start_url="https://en.wikipedia.org/wiki/Main_Page",
        max_steps=5
    )

    orchestrator.print_summary(result)


async def test_youtube_search():
    """Test 6: Search on a non-Google site (different search interface)
    Tests: type action on a site with its own search, click video result
    """
    executor = Executor(headless=False)
    planner = Planner(model="gpt-4o")
    orchestrator = Orchestrator(executor, planner)

    print("\n📝 Test: Search on YouTube and click first result")

    result = await orchestrator.run(
        user_goal="search for 'reinforcement learning explained' on YouTube and click the first video",
        start_url="https://www.youtube.com",
        max_steps=6
    )

    orchestrator.print_summary(result)


async def test_dropdown_sort():
    """Test 7: E-commerce sort with dropdown - tests select action
    Tests: select action (dropdown), multi-step navigation, price sorting
    """
    executor = Executor(headless=False)
    planner = Planner(model="gpt-4o")
    orchestrator = Orchestrator(executor, planner)

    print("\n📝 Test: Search on Amazon and sort by price low to high")

    result = await orchestrator.run(
        user_goal="search for 'mechanical keyboard' on Amazon and sort results by price: low to high",
        start_url="https://www.amazon.com",
        max_steps=8
    )

    orchestrator.print_summary(result)


async def test_github_navigation():
    """Test 8: Multi-step navigation on GitHub
    Tests: search on GitHub, navigate to specific repo page
    """
    executor = Executor(headless=False)
    planner = Planner(model="gpt-4o")
    orchestrator = Orchestrator(executor, planner)

    print("\n📝 Test: Find the Playwright GitHub repo")

    result = await orchestrator.run(
        user_goal="go to the microsoft/playwright repository on GitHub",
        start_url="https://github.com",
        max_steps=6
    )

    orchestrator.print_summary(result)


async def test_vision_complex_page():
    """Test 9: Vision on a page with many elements (Amazon product page)
    Tests: vision guidance when num_elements > 50 triggers vision automatically
    """
    executor = Executor(headless=False, use_vision=False)  # Orchestrator will trigger vision based on page complexity
    planner = Planner(model="gpt-4o")
    orchestrator = Orchestrator(executor, planner, use_vision=False)

    print("\n📝 Test (VISION): Find cheapest laptop stand on Amazon")

    result = await orchestrator.run(
        user_goal="find the cheapest laptop stand on Amazon and open the product page",
        start_url="https://www.amazon.com",
        max_steps=10
    )

    orchestrator.print_summary(result)


if __name__ == "__main__":
    print("Choose test:")
    print("1. Simple navigation (go to Github)")
    print("2. Search and click (RLHF tech report)")
    print("3. Complex task (cheapest toothbrush on Amazon)")
    print("4. WITH VISION: cheapest toothbrush on Amazon")
    print("--- New Tests ---")
    print("5. Direct navigation + scroll (Wikipedia LLM page)")
    print("6. Non-Google search (YouTube reinforcement learning video)")
    print("7. Dropdown sort (Amazon mechanical keyboard, sort by price)")
    print("8. Multi-step site navigation (GitHub Playwright repo)")
    print("9. WITH VISION: Complex page (cheapest laptop stand on Amazon)")

    choice = input("Enter choice (1-9): ").strip()

    if choice == "1":
        asyncio.run(test_simple_task())
    elif choice == "2":
        asyncio.run(test_search_task())
    elif choice == "3":
        asyncio.run(test_complex_task())
    elif choice == "4":
        asyncio.run(test_with_vision())
    elif choice == "5":
        asyncio.run(test_direct_navigation())
    elif choice == "6":
        asyncio.run(test_youtube_search())
    elif choice == "7":
        asyncio.run(test_dropdown_sort())
    elif choice == "8":
        asyncio.run(test_github_navigation())
    elif choice == "9":
        asyncio.run(test_vision_complex_page())
    else:
        print("Invalid choice")
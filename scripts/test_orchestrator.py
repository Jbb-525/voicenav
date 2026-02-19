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
from core.planner import TextPlanner, VisionPlanner
from core.orchestrator import Orchestrator

async def test_with_vision():
    """Test with VisionPlanner"""
    executor = Executor(headless=False)
    planner = VisionPlanner(model="gpt-4o")  # ← 使用 VisionPlanner
    orchestrator = Orchestrator(executor, planner)
    
    print("\n📝 Test: Complex task with VisionPlanner")
    
    result = await orchestrator.run(
        user_goal="find the cheapest toothbrush on Amazon",
        start_url="https://www.google.com",
        max_steps=10
    )
    
    orchestrator.print_summary(result)


async def test_search_task():
    """Test search with TextPlanner"""
    executor = Executor(headless=False)
    planner = TextPlanner(model="gpt-4o-mini")  # ← 使用 TextPlanner
    orchestrator = Orchestrator(executor, planner)
    
    print("\n📝 Test: Search and click first result")
    
    result = await orchestrator.run(
        user_goal="search for RLHF tech report from openai",
        start_url="https://www.google.com",
        max_steps=6
    )
    
    orchestrator.print_summary(result)

 

async def test_without_vision():
    """Test complex task without vision assistance"""
    executor = Executor(headless=False)
    planner = TextPlanner(model="gpt-4o")
    orchestrator = Orchestrator(executor, planner)
    
    print("\n" + "="*60)
    print("TESTING WITHOUT VISION ASSISTANCE")
    print("="*60)
    
    print("\n📝 Test: Find cheapest product on Amazon")
    
    result = await orchestrator.run(
        user_goal="find the cheapest toothbrush on Amazon",
        start_url="https://www.google.com",
        max_steps=10  # More steps for complex task
    )
    
    orchestrator.print_summary(result)

if __name__ == "__main__":
    print("Choose test:")
    print("1. Complex task with vison (cheapest toothbrush on Amazon)")
    print("2. Complex task without vison (cheapest toothbrush on Amazon)")
    print("3. Search and click first result (RLHF tech report)")

    choice = input("Enter choice (1-3): ").strip()

    if choice == "1":
        asyncio.run(test_with_vision())
    elif choice == "2":
        asyncio.run(test_without_vision())
    elif choice == "3":
        asyncio.run(test_search_task())
    else:
        print("Invalid choice")
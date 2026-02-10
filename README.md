# Development Log

## Phase 1: Core Pipeline (Complete ✅)

### Date: Feb 2026

#### Accomplished
1. **Project Setup**
   - Created virtual environment
   - Set up project structure
   - Configured dependencies

2. **Executor Layer**
   - Implemented browser automation with Playwright
   - Built Accessibility Tree extraction
   - Created 5 basic actions: goto, click, type, scroll, done
   - Added screenshot capability
   - Handled dynamic page states (e.g., dropdown menus)

3. **Planner Layer**
   - Integrated GPT-4o-mini
   - Designed Pydantic models for structured outputs
   - Resolved OpenAI schema validation issues
   - Created action type unions (GotoAction, ClickAction, etc.)

4. **Integration Testing**
   - Successfully tested: "search for Python tutorials"
   - Successfully tested: "go to github.com"
   - Validated Planner → Executor pipeline

#### Key Challenges & Solutions

**Challenge 1: Accessibility Tree vs Raw HTML**
- Problem: Should we use raw HTML or Accessibility Tree?
- Solution: Chose Accessibility Tree for token efficiency and semantic clarity
- Result: 10-50x reduction in tokens

**Challenge 2: Dynamic Page States**
- Problem: Elements change after user input (e.g., search suggestions)
- Solution: Use `submit=true` in type action instead of clicking buttons
- Learning: Accessibility Tree is a snapshot; pages are dynamic

**Challenge 3: Pydantic Schema for OpenAI**
- Problem: `'required' array including every key in properties` error
- Solution: Used Union types for different action classes
- Result: Clean, type-safe action definitions

**Challenge 4: Element Matching**
- Problem: Finding elements by name from Accessibility Tree
- Solution: Multiple fallback strategies using `get_by_role(role, name=name)`
- Result: Robust element finding

#### Technical Decisions

1. **Why GPT-4o-mini over Gemini?**
   - More stable API
   - Better structured output support
   - Can switch later for comparison

2. **Why text input first?**
   - Faster iteration
   - Easier debugging
   - Voice is just STT wrapper

3. **Why Pydantic Union types?**
   - OpenAI structured output compatibility
   - Type safety
   - Clear action schemas

#### Metrics
- Lines of code: ~500
- Test scenarios: 2
- Success rate: 100% (when no CAPTCHA)
- Token usage: ~1k tokens per decision

---

## Phase 2: Multi-Step & Voice (In Progress 🔄)

### Goals
- [ ] Build Orchestrator for multi-step tasks
- [ ] Add voice input (Perceiver layer)
- [ ] Implement task completion detection
- [ ] Add error recovery

### Next Steps
1. Design Orchestrator loop logic
2. Add conversation history/context
3. Test complex tasks (e.g., "search and click first result")
4. Integrate Deepgram for voice input

---

## Future Phases

### Phase 3: Production Backend
- FastAPI server
- WebSocket for real-time updates
- Multi-session management
- Rate limiting and auth

### Phase 4: Frontend
- Next.js UI
- Microphone button
- Live action stream
- Screenshot gallery
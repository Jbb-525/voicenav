"""
Vision: Uses GPT-4o vision to analyze screenshots and guide element selection
"""
from openai import OpenAI
from typing import Dict, Any, Optional, List
import base64
import os
from dotenv import load_dotenv

load_dotenv()


class VisionAnalyzer:
    """Vision-based page analyzer for web automation"""
    
    def __init__(self, model: str = "gpt-4o"):
        """
        Initialize vision analyzer
        
        Args:
            model: OpenAI vision model (gpt-4o or gpt-4o-mini with vision)
        """
        self.model = model
        self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        
        self.analysis_prompt_template = """You are a web automation assistant analyzing a webpage screenshot.

Your task: Help identify the correct element to interact with for accomplishing the user's goal.

User's Goal: {user_goal}

Current Page Information:
- URL: {url}
- Title: {title}
- Total Interactive Elements: {total_elements}

Please analyze the screenshot and identify the target element needed to accomplish the goal.

Return your analysis in this EXACT JSON format:
{{
  "target_element": {{
    "primary_identifier": "The main visible text on the element (exact text you see)",
    "element_role": "input|button|link|dropdown|checkbox",
    "visual_prominence": "primary|secondary|tertiary",
    "location_hint": "top-left|top-center|top-right|middle-left|middle-center|middle-right|bottom-left|bottom-center|bottom-right",
    "description": "Brief description of the element and why it's the right choice"
  }},
  "page_context": {{
    "page_type": "search_engine|e-commerce|social_media|documentation|other",
    "main_content_area": "Description of what dominates the page",
    "complexity": "simple|moderate|complex"
  }},
  "alternatives": [
    {{
      "primary_identifier": "Alternative element text if main choice uncertain",
      "confidence": 0.7
    }}
  ],
  "confidence": 0.95
}}

Guidelines:
1. primary_identifier should be the EXACT text visible on the element (not paraphrased)
2. For search boxes, include placeholder text or nearby label text
3. visual_prominence: "primary" = main action, "secondary" = supporting, "tertiary" = minor
4. If multiple similar elements exist, list them in alternatives
5. Be specific but concise

Focus on finding THE MOST RELEVANT element for the user's goal, not just any matching element."""

    async def analyze_page(
        self,
        screenshot_base64: str,
        user_goal: str,
        page_info: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """
        Analyze page screenshot to identify target element
        
        Args:
            screenshot_base64: Base64 encoded screenshot
            user_goal: User's objective
            page_info: Dict with url, title, total_elements
            
        Returns:
            Analysis result with target element description
        """
        try:
            # Format prompt with page info
            prompt = self.analysis_prompt_template.format(
                user_goal=user_goal,
                url=page_info.get('url', 'Unknown'),
                title=page_info.get('title', 'Unknown'),
                total_elements=page_info.get('total_elements', 0)
            )
            
            print(f"\n🔍 Vision Analysis Starting...")
            print(f"   Model: {self.model}")
            
            # Call OpenAI Vision API
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": prompt
                            },
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/png;base64,{screenshot_base64}",
                                    "detail": "high"
                                }
                            }
                        ]
                    }
                ],
                max_tokens=1000,
                temperature=0
            )
            
            # Parse response
            content = response.choices[0].message.content
            
            # Try to extract JSON from response
            import json
            
            # Remove markdown code blocks if present
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()
            
            analysis = json.loads(content)
            
            print(f"✅ Vision Analysis Complete")
            print(f"   Target: {analysis['target_element']['primary_identifier']}")
            print(f"   Confidence: {analysis.get('confidence', 'N/A')}")
            
            return analysis
            
        except Exception as e:
            print(f"❌ Vision analysis failed: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def match_element_by_description(
        self,
        vision_desc: Dict[str, Any],
        ax_elements: List[Dict[str, Any]]
    ) -> Optional[Dict[str, Any]]:
        """
        Match vision description to accessibility tree element
        
        Args:
            vision_desc: Vision model's target_element description
            ax_elements: List of accessibility tree elements
            
        Returns:
            Best matching element or None
        """
        if not vision_desc or not ax_elements:
            return None
        
        target = vision_desc.get('target_element', {})
        primary_id = target.get('primary_identifier', '').lower()
        element_role = target.get('element_role', '')
        description = target.get('description', '')
        # Special handling for dropdowns
        if element_role == 'dropdown':
            print(f"   📋 Dropdown detected - looking for combobox/listbox")
            
            # Try to extract dropdown name from description or primary_id
            # Look for combobox in elements
            for elem in ax_elements:
                if elem.get('role') in ['combobox', 'listbox']:
                    elem_name = elem.get('name', '').lower()
                    # Match if primary_id contains combobox name or vice versa
                    if elem_name in primary_id or primary_id in elem_name:
                        print(f"   ✅ Found dropdown: [{elem['role']}] {elem['name']}")
                        # Return the combobox itself, not the option
                        return elem
        
        print(f"\n🎯 Matching Vision Description to Elements...")
        print(f"   Looking for: '{primary_id}' (role: {element_role})")
        
        # Role mapping
        role_map = {
            'input': ['searchbox', 'textbox', 'combobox'],
            'button': ['button'],
            'link': ['link'],
            'dropdown': ['combobox', 'listbox'],
            'checkbox': ['checkbox'],
        }
        
        expected_roles = role_map.get(element_role, [])
        
        # Score each element
        candidates = []
        
        for elem in ax_elements:
            score = 0
            elem_name = elem.get('name', '').lower()
            elem_role = elem.get('role', '')
            
            # Text matching (most important)
            if primary_id in elem_name:
                score += 10
                # Exact match bonus
                if primary_id == elem_name:
                    score += 5
            elif elem_name in primary_id:
                score += 7
            
            # Partial word match
            primary_words = set(primary_id.split())
            elem_words = set(elem_name.split())
            common_words = primary_words & elem_words
            score += len(common_words) * 2
            
            # Role matching
            if expected_roles and elem_role in expected_roles:
                score += 5
            
            # Only consider elements with some match
            if score > 0:
                candidates.append({
                    'element': elem,
                    'score': score,
                    'name': elem_name,
                    'role': elem_role
                })
        
        # Sort by score
        candidates.sort(key=lambda x: x['score'], reverse=True)
        
        if candidates:
            best = candidates[0]
            print(f"✅ Best match found:")
            print(f"   Element: [{best['role']}] {best['name']}")
            print(f"   Score: {best['score']}")
            
            # Show alternatives if close scores
            if len(candidates) > 1 and candidates[1]['score'] >= best['score'] * 0.8:
                print(f"   ⚠️  Close alternative exists:")
                print(f"      [{candidates[1]['role']}] {candidates[1]['name']}")
            
            return best['element']
        
        # Try alternatives from vision output
        alternatives = vision_desc.get('alternatives', [])
        if alternatives:
            print(f"   ⚠️  No match for primary, trying alternatives...")
            for alt in alternatives:
                alt_id = alt.get('primary_identifier', '').lower()
                for elem in ax_elements:
                    if alt_id in elem.get('name', '').lower():
                        print(f"   ✅ Matched alternative: {elem['name']}")
                        return elem
        
        print(f"   ❌ No matching element found")
        return None
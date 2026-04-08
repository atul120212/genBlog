import textstat
import re

def calculate_readability_score(text):
    if not text or len(text.strip()) == 0:
        return 0
    # Returns Flesch Reading Ease score, scale 0-100
    # Higher is easier to read.
    try:
        score = textstat.flesch_reading_ease(text)
        # Cap score between 0 and 100 for ui purposes
        return max(0, min(100, int(score)))
    except:
        return 50 # Default score if calculation fails

def calculate_seo_score(content, meta_title, meta_description, keywords):
    score = 0
    if not content: return 0

    word_count = len(content.split())
    
    # 1. Length check (ideal > 300 words)
    if word_count > 300:
        score += 20
    elif word_count > 100:
        score += 10
        
    # 2. Meta title check
    if meta_title and 10 <= len(meta_title) <= 60:
        score += 15
        
    # 3. Meta description check
    if meta_description and 50 <= len(meta_description) <= 160:
        score += 15
        
    # 4. Keywords
    keyword_list = [k.strip().lower() for k in keywords.split(',')] if keywords else []
    if len(keyword_list) > 0:
        score += 10
        
    # 5. Headings check
    has_h2 = '## ' in content or '<h2>' in content.lower()
    has_h3 = '### ' in content or '<h3>' in content.lower()
    
    if has_h2: score += 15
    if has_h3: score += 10

    # 6. Keyword density (fuzzy check)
    content_lower = content.lower()
    found_keywords = sum(1 for k in keyword_list if k in content_lower)
    if found_keywords > 0:
        score += 15
        
    return max(0, min(100, int(score)))

def calculate_engagement_score(content):
    # Heuristic based on questions, exclamations, lists, bold text
    score = 50 
    if not content: return 0
    
    if '?' in content: score += 10
    if '!' in content: score += 10
    
    # Check for lists
    if '- ' in content or '* ' in content:
        score += 15
        
    # Check for formatting
    if '**' in content: 
        score += 15
        
    return max(0, min(100, int(score)))

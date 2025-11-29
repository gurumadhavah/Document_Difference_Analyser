import os
import difflib
from fastapi import FastAPI
from pydantic import BaseModel
from dotenv import load_dotenv
from huggingface_hub import InferenceClient

load_dotenv()
app = FastAPI()
HF_API_KEY = os.getenv("HUGGINGFACE_API_KEY")
client = InferenceClient(token=HF_API_KEY)

class DocumentRequest(BaseModel):
    text_a: str
    text_b: str

def get_inline_diff(text_a, text_b):
    """
    Compares two strings word-by-word and wraps changes in HTML spans.
    Returns: (highlighted_a, highlighted_b)
    """
    # Split into words to compare granularly
    a_words = text_a.split()
    b_words = text_b.split()
    matcher = difflib.SequenceMatcher(None, a_words, b_words)
    
    out_a = []
    out_b = []
    
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        # Get the words involved in this change
        wa = a_words[i1:i2]
        wb = b_words[j1:j2]
        
        chunk_a = " ".join(wa)
        chunk_b = " ".join(wb)
        
        if tag == 'equal':
            # No change, just append text
            out_a.append(chunk_a)
            out_b.append(chunk_b)
        elif tag == 'replace':
            # Highlighting specific words!
            out_a.append(f'<span class="diff-del">{chunk_a}</span>')
            out_b.append(f'<span class="diff-add">{chunk_b}</span>')
        elif tag == 'delete':
            out_a.append(f'<span class="diff-del">{chunk_a}</span>')
        elif tag == 'insert':
            out_b.append(f'<span class="diff-add">{chunk_b}</span>')
            
    return " ".join(out_a), " ".join(out_b)

def generate_json_diff(text_a, text_b):
    a_lines = text_a.splitlines()
    b_lines = text_b.splitlines()
    
    # Compare lines first to keep the table structure
    matcher = difflib.SequenceMatcher(None, a_lines, b_lines)
    diff_data = []

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        chunk_a = "\n".join(a_lines[i1:i2])
        chunk_b = "\n".join(b_lines[j1:j2])
        
        if tag == 'equal':
            diff_data.append({"type": "equal", "original": chunk_a, "modified": chunk_b})
        elif tag == 'replace':
            # Run the GRANULAR word-level diff on these lines
            hl_a, hl_b = get_inline_diff(chunk_a, chunk_b)
            diff_data.append({"type": "replace", "original": hl_a, "modified": hl_b})
        elif tag == 'delete':
            # If a whole line is deleted, mark it all as deleted
            hl_a = f'<span class="diff-del">{chunk_a}</span>'
            diff_data.append({"type": "delete", "original": hl_a, "modified": ""})
        elif tag == 'insert':
            # If a whole line is added, mark it all as added
            hl_b = f'<span class="diff-add">{chunk_b}</span>'
            diff_data.append({"type": "insert", "original": "", "modified": hl_b})
            
    return diff_data

def summarize_diff_with_ai(diff_text):
    if not diff_text.strip(): return "No differences found."
    user_message = f"""
    Analyze the differences below.
    Format output as:
    **Key Changes:**
    * [Point 1]
    **Tone:** [Analysis]
    
    DIFF:
    {diff_text}
    """
    try:
        response = client.chat_completion(
            messages=[{"role": "user", "content": user_message}],
            model="Qwen/Qwen2.5-72B-Instruct", 
            max_tokens=250
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"AI Error: {e}"

@app.post("/compare")
async def compare_documents(request: DocumentRequest):
    diff = difflib.unified_diff(request.text_a.splitlines(), request.text_b.splitlines(), lineterm='')
    text_diff = "\n".join(list(diff))
    
    # Get the "Smart" JSON diff
    json_diff = generate_json_diff(request.text_a, request.text_b)
    
    ai_summary = summarize_diff_with_ai(text_diff)
    
    return {
        "diff": text_diff,
        "json_diff": json_diff,
        "summary": ai_summary
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
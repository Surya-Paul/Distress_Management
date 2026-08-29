"""
test_groq_connection.py — Phase 1: Verify Groq API connection.
Sends a single test prompt and prints the response + latency.
"""

import os
import time
from dotenv import load_dotenv
from groq import Groq

load_dotenv()

def main():
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        print("ERROR: GROQ_API_KEY not found in environment. Check your .env file.")
        return

    client = Groq(api_key=api_key)
    
    print("Testing Groq API connection...")
    print(f"Model: openai/gpt-oss-20b")
    print("-" * 50)
    
    start = time.time()
    
    chat_completion = client.chat.completions.create(
        messages=[
            {
                "role": "system",
                "content": "You are a mental health assessment assistant. Respond concisely."
            },
            {
                "role": "user",
                "content": "Reply with the word 'connected'."
            }
        ],
        model="openai/gpt-oss-20b",
        temperature=0.3,
        max_tokens=150,
    )
    
    elapsed = time.time() - start
    
    response = chat_completion.choices[0].message.content
    print(f"Response: {response}")
    print(f"Latency: {elapsed:.2f}s")
    print(f"Tokens used: {chat_completion.usage.total_tokens}")
    print("-" * 50)
    print("✅ Groq connection successful!")

if __name__ == "__main__":
    main()

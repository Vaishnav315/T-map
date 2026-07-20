import asyncio
import cv2
import numpy as np
import ollama

async def test_llava():
    # 1. Create a dummy image
    img = np.zeros((480, 640, 3), dtype=np.uint8)
    
    # Draw a simulated motion trail (Yellow to Red)
    cv2.line(img, (100, 100), (200, 200), (0, 255, 255), 3) # Yellow
    cv2.line(img, (200, 200), (300, 300), (0, 0, 255), 3)   # Red
    
    # Draw a red bounding box around the "person"
    cv2.rectangle(img, (250, 250), (350, 450), (0, 0, 255), 3)
    
    # Encode to bytes
    _, buffer = cv2.imencode(".jpg", img)
    image_bytes = buffer.tobytes()
    
    prompts = {
        "Strict Constraint (Old)": (
            "Look at the person inside the red box. Are they climbing? Answer with exactly 'YES' or 'NO', followed by a one sentence description. "
            "(Note: The colored line from yellow to red indicates their recent motion path.)"
        ),
        "Conversational": (
            "Please describe what is happening inside the red bounding box. The yellow-to-red line shows the path the person recently moved. "
            "Based on this, do you think they are climbing a wall or fence?"
        ),
        "VQA Format": (
            "Question: Is the person inside the red box climbing a wall or fence? The yellow-to-red line shows their movement. Answer:"
        ),
        "Roleplay": (
            "You are a security AI. Analyze the red box in this image. The yellow-to-red line shows movement. "
            "State 'CLIMBING' if they are climbing, or 'NORMAL' if not."
        )
    }
    
    print("Testing Llava with different prompt strategies...\n")
    client = ollama.AsyncClient()
    
    for name, p in prompts.items():
        print(f"--- Strategy: {name} ---")
        print(f"Prompt: {p}")
        try:
            res = await client.generate(
                model='llava:latest', 
                prompt=p, 
                images=[image_bytes],
                options={"temperature": 0.0, "num_predict": 50}
            )
            print(f"LLAVA RESPONSE: {res.get('response').strip()}\n")
        except Exception as e:
            print(f"Error: {e}\n")

if __name__ == "__main__":
    asyncio.run(test_llava())

import os
import time
import requests

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

IMAGE_PATH = os.path.join(BASE_DIR, "images", "bus.jpg")
INCORRECT_FILETYPE_PATH = os.path.join(BASE_DIR, "models", "imagenet_classes.txt")  # used to simulate errors

TARGET_URL = "http://localhost:8001/predict"

print(f"--- Starting Traffic Generator ---")
print(f"Target URL : {TARGET_URL}")
print(f"Image path : {IMAGE_PATH}")

count = 0

while True:
    try:
        # Simulate an error for every 20 requests
        image_file_loc = INCORRECT_FILETYPE_PATH if count % 20 == 0 else IMAGE_PATH

        with open(image_file_loc, "rb") as f:
            files = {
                "file": (os.path.basename(image_file_loc), f, "image/jpeg")
            }

            start = time.time()
            response = requests.post(TARGET_URL, files=files, timeout=10)
            elapsed = time.time() - start

        count += 1
        print(f"Request #{count}: [{response.status_code}] took {elapsed:.3f}s")

    except Exception as e:
        print(f"Error occurred: {e}")

    time.sleep(1)

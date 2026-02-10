from kiteconnect import KiteConnect
import os
from dotenv import load_dotenv
import webbrowser

# Load environment variables
load_dotenv()

def get_access_token():
    api_key = os.getenv("KITE_API_KEY")
    api_secret = os.getenv("KITE_API_SECRET")

    if not api_key or not api_secret:
        print("Error: KITE_API_KEY or KITE_API_SECRET is missing in .env file")
        return

    kite = KiteConnect(api_key=api_key)

    print("Generating Login URL...")
    login_url = kite.login_url()
    print(f"Login URL: {login_url}")
    
    print("\nOpening browser to login...")
    webbrowser.open(login_url)
    
    print("\n1. Login to Kite in the browser.")
    print("2. You will be redirected to a URL (e.g. http://127.0.0.1/?status=success&request_token=xyz...)")
    print("3. Copy the 'request_token' from that URL.")
    
    request_token = input("\nPaste the request_token here: ").strip()
    
    try:
        data = kite.generate_session(request_token, api_secret=api_secret)
        access_token = data["access_token"]
        print("\n" + "="*50)
        print("SUCCESS! Here is your Access Token:")
        print(f"\n{access_token}\n")
        print("="*50)
        print("Copy this token and paste it into config.py as the 'access_token' value.")
    except Exception as e:
        print(f"\nError generating session: {e}")

if __name__ == "__main__":
    get_access_token()

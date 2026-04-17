import win32com.client
import os

def debug_outlook():
    try:
        outlook = win32com.client.Dispatch("Outlook.Application")
        session = outlook.Session
        print("--- Outlook Accounts ---")
        for acc in session.Accounts:
            print(f"Prop: {acc.SmtpAddress} (Name: {acc.DisplayName})")
        
        print("\n--- Default Email Env ---")
        print(f"EMAIL_USER: {os.getenv('EMAIL_USER')}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    debug_outlook()

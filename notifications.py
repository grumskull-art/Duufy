import firebase_admin
from firebase_admin import messaging


def send_push_notification(tokens, title, body):
    try:
        message = messaging.MulticastMessage(
            notification=messaging.Notification(title=title, body=body), tokens=tokens
        )
        response = messaging.send_multicast(message)
        print(f"📱 Sent {response.success_count} notifications.")
        return True
    except Exception as e:
        print(f"⚠️ Push notification failed (Firebase not set up): {e}")
        return False

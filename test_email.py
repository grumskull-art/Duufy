"""
Test email invitation
"""
from invitations import create_invitation

# Test invitation
print("🧪 Tester email invitation...\n")

test_email = input("Indtast din email: ")

result = create_invitation(
    group_id="test-group-123",
    group_name="Test Familie",
    inviter_name="Thore",
    email=test_email,
    base_url="https://unsophomoric-nila-collaterally.ngrok-free.dev"
)

print("\n" + "="*50)
if result["success"]:
    print("✅ EMAIL SENDT!")
    print(f"📧 Til: {test_email}")
    print(f"🔗 Invitation link: {result['invite_url']}")
    print(f"📮 Email ID: {result.get('email_id', 'N/A')}")
    print("\n💡 Tjek din indbakke (også spam folder!)")
else:
    print("❌ FEJL!")
    print(f"Message: {result['message']}")
print("="*50)

"""
Quick email test til grumskull@gmail.com
"""

from invitations import create_invitation

print("📧 Sender test invitation til grumskull@gmail.com...\n")

result = create_invitation(
    group_id="test-group-123",
    group_name="Min Familie",
    inviter_name="Thore",
    email="grumskull@gmail.com",
    base_url="https://unsophomoric-nila-collaterally.ngrok-free.dev",
)

print("=" * 60)
if result["success"]:
    print("✅ EMAIL SENDT TIL grumskull@gmail.com!")
    print(f"\n🔗 Invitation link:")
    print(f"   {result['invite_url']}")
    if result.get("email_id"):
        print(f"\n📮 Email ID: {result['email_id']}")
    print("\n💡 Tjek din Gmail indbakke (også spam/promotions!)")
else:
    print("❌ FEJL:")
    print(f"   {result['message']}")
print("=" * 60)

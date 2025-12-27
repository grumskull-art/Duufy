from invitations import create_invitation
import random

group_id = f'test-{random.randint(1000,9999)}'

result = create_invitation(
    group_id=group_id,
    group_name='Duufy Test 🚀',
    inviter_name='GitHub Copilot',
    email='grumskull@gmail.com',
    base_url='https://unsophomoric-nila-collaterally.ngrok-free.dev'
)

print('='*60)
if result['success']:
    print('✅ TEST EMAIL SENDT!')
    print(f'📧 Til: grumskull@gmail.com')
    print(f'🔗 Link: {result["invite_url"]}')
    print(f'📮 Email ID: {result.get("email_id", "N/A")}')
    print('\n💡 Tjek din Gmail (også spam folder!)')
else:
    print(f'❌ Fejl: {result["message"]}')
print('='*60)

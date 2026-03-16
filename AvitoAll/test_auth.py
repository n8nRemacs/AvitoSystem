"""Quick test script for Avito auth"""
from avito_auth import AvitoAuth, DeviceProfile, AuthStatus
import json

# Use existing device_id from captured session
device = DeviceProfile.oneplus9_pro(device_id='a8d7b75625458809')
print(f'Device ID: {device.device_id}')
print(f'User-Agent: {device.user_agent}')

auth = AvitoAuth(device=device)

# Warmup
print('\n--- Warmup ---')
auth.warmup()

# Login
print('\n--- Login ---')
result = auth.login('+79997253777', '31415926Mips')

print(f'\nStatus: {result.status}')
if result.error_message:
    print(f'Error: {result.error_message}')

if result.raw_response:
    print(f'\nRaw response:')
    print(json.dumps(result.raw_response, indent=2, ensure_ascii=False))

if result.status == AuthStatus.SUCCESS:
    print(f'\n=== SUCCESS ===')
    print(f'User ID: {result.user_id}')
    print(f'User Name: {result.user_name}')
    print(f'Session: {result.session[:60]}...')
    print(f'Refresh Token: {result.refresh_token}')
    auth.save_session('avito_auth_session.json')

elif result.status == AuthStatus.TFA_REQUIRED:
    print(f'\n=== TFA REQUIRED ===')
    print(f'Flow: {result.tfa_flow}')
    print(f'Phone: {result.tfa_phone}')
    if result.tfa_phone_list:
        print(f'Phone list: {result.tfa_phone_list}')

    # Save state for TFA continuation
    with open('tfa_state.json', 'w') as f:
        json.dump({
            'tracker_uid': auth.tracker_uid,
            'device': device.to_dict(),
            'tfa_flow': result.tfa_flow
        }, f, indent=2)
    print('\nState saved to tfa_state.json - waiting for SMS code...')

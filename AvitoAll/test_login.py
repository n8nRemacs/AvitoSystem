"""Quick login test"""
from avito_auth_final import AvitoAuthFinal

auth = AvitoAuthFinal()

# Test with new credentials
phone = "+79171708077"
password = "Mi31415926pSss!"

print(f"Phone: {phone}")
print(f"Password: {password}")
print(f"Fingerprint: {auth.session_data.fingerprint[:50]}...")

result = auth.login(phone, password, geo="46.360889;48.047291;100;1768295137")

if result.get("status") == "ok":
    print(f"\n[+] SUCCESS!")
    print(f"    User ID: {result.get('user', {}).get('id')}")
    auth.save_session("avito_session_new.json")
    print("[+] Session saved to avito_session_new.json")
else:
    print(f"[-] Failed: {result.get('status')}")

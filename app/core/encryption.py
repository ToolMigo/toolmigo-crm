import base64, hashlib
from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings

def cipher():
    key=base64.urlsafe_b64encode(hashlib.sha256(settings.SECRET_KEY.encode()).digest())
    return Fernet(key)

def encrypt_secret(value): return cipher().encrypt(value.encode()).decode()

def decrypt_secret(value):
    try: return cipher().decrypt(value.encode()).decode()
    except InvalidToken: raise ValueError('Het opgeslagen SMTP-wachtwoord kan niet worden ontsleuteld. Sla het opnieuw op.')

# scripts/generate_keys.py
# Generates RSA key pair for JWT signing
# Run once: python scripts/generate_keys.py

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.backends import default_backend

private_key = rsa.generate_private_key(public_exponent=65537,
                                       key_size=2048,
                                       backend= default_backend)

private_pem = private_key.private_bytes(
    encoding= serialization.Encoding.PEM,
    format=serialization.PrivateFormat.TraditionalOpenSSL,
    encryption_algorithm= serialization.NoEncryption()
    
).decode()

public_pem = private_key.public_key().public_bytes(
    encoding=serialization.Encoding.PEM,
    format=serialization.PublicFormat.SubjectPublicKeyInfo
).decode()

print("\n=== PRIVATE KEY (JWT_PRIVATE_KEY) ===")
print(private_pem)
print("\n=== PUBLIC KEY (JWT_PUBLIC_KEY) ===")
print(public_pem)
print("\nCopy these into your .env file")
print("Replace newlines with \\n")
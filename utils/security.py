import bcrypt

def hash_password(password: str) -> str:
    """Hashes a password using bcrypt."""
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password.encode('utf-8'), salt)
    return hashed.decode('utf-8')

def check_password(password: str, hashed: str) -> bool:
    """Checks a password against a bcrypt hash. Returns True if it matches, False otherwise."""
    # If the database contains plain text passwords, we can fallback or just fail.
    # To handle the migration, we'll try bcrypt, and if it fails due to ValueError,
    # we return whether they exactly match (which means plain text hasn't been migrated yet).
    try:
        return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))
    except ValueError:
        # Fallback for plain-text passwords before migration
        return password == hashed

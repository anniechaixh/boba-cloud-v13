"""Server administrator only: reset a Student ID PIN without email.
Run from the server console: python reset_student_pin.py STUDENT_ID
"""
import getpass
import sys
import sqlite3
import secrets
import re
from server import DB_PATH, pw_hash


def main():
    if len(sys.argv) != 2:
        raise SystemExit('Usage: python reset_student_pin.py STUDENT_ID')
    username = sys.argv[1].strip().lower()
    if not re.fullmatch(r'[a-z0-9][a-z0-9_.-]{2,23}', username):
        raise SystemExit('Invalid Student ID.')
    pin = getpass.getpass('New 6–8 digit PIN: ')
    confirm = getpass.getpass('Confirm PIN: ')
    if pin != confirm or not re.fullmatch(r'\d{6,8}', pin):
        raise SystemExit('PINs did not match or were invalid.')
    salt = secrets.token_hex(16)
    with sqlite3.connect(DB_PATH) as db:
        result = db.execute('UPDATE students SET salt=?, pin_hash=? WHERE username=?',
                            (salt,pw_hash(pin,salt),username))
        if result.rowcount != 1:
            raise SystemExit('Student ID not found.')
        db.execute('DELETE FROM sessions WHERE username=?',(username,))
        db.commit()
    print('PIN updated. Existing sessions have been signed out.')

if __name__ == '__main__':
    main()

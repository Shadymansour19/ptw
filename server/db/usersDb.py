"""Data access layer for the `users` table, including bcrypt password
hashing/verification and first-boot admin account seeding."""

import secrets
import logging
import bcrypt
from psycopg2.extras import RealDictCursor

from models.User import User, UserRoles, SecuredUser
from db.commonDb import CommonDB


log = logging.getLogger(__name__)


def _hash_password(plain: str) -> str:
    """Hash a plaintext password with bcrypt (random per-call salt)."""
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()

def _verify_password(plain: str, hashed: str) -> bool:
    """Check a plaintext password against a bcrypt hash, returning False
    (rather than raising) on empty input or a malformed hash."""
    if not plain or not hashed:
        return False
    try:
        return bcrypt.checkpw(plain.encode(), hashed.encode())
    except Exception:
        return False


class UsersDb:
    """Data access layer for user accounts: credential verification, CRUD, and
    per-user settings (theme, active status)."""

    def __init__(self):
        """Assumes the `users` table already exists — run server/dev-scripts/init_db.py once
        before first starting the server. Only seeds the initial admin account if the
        table is empty, with must_change_password set so it's forced to change the
        generated password on its first login."""
        with CommonDB.get_conn() as conn:
            try:
                with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                    cursor.execute("SELECT COUNT(*) FROM users")
                    if cursor.fetchone()['count'] == 0:
                        seed_password = secrets.token_urlsafe(12)
                        cursor.execute('''
                            INSERT INTO users (username, password, name, role, department, email, must_change_password)
                            VALUES (%s, %s, %s, %s, %s, %s, %s)''',
                            ("admin", _hash_password(seed_password), "Administrator", UserRoles.ADMIN, "Admin", "", True)
                        )
                        log.warning("=" * 60)
                        log.warning("INITIAL ADMIN PASSWORD: %s", seed_password)
                        log.warning("Change this immediately after first login.")
                        log.warning("=" * 60)
                conn.commit()
            except Exception as e:
                raise Exception("Error initializing users database: " + str(e))

    def isUsernameExists(self, username: str):
        """Return True if a user row with this username exists, False on any
        error or if it doesn't (never raises)."""
        try:
            with CommonDB.get_conn() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                    cursor.execute("SELECT username FROM users WHERE username = %s", (username,))
                    return cursor.fetchone() is not None
        except Exception:
            return False

    def getVerifiedUser(self, username: str, password: str) -> User | None:
        """Look up the user by username and verify the given password against
        its stored bcrypt hash.

        Returns:
            A User instance if the username exists and the password matches,
            otherwise None. Does not check whether the account is active.

        Raises:
            Exception: wrapping any underlying database error.
        """
        try:
            with CommonDB.get_conn() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                    cursor.execute("SELECT * FROM users WHERE username = %s", (username,))
                    row = cursor.fetchone()
            if row and _verify_password(password, row['password']):
                return User().setAll(row)
            return None
        except Exception:
            raise Exception("Error verifying user credentials")

    def updateUserPassword(self, username: str, newPassword: str):
        """Hash and set a new password for the given username (used by the
        password reset flow).

        Raises:
            Exception: wrapping any underlying database error.
        """
        try:
            with CommonDB.get_conn() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                    cursor.execute(
                        'UPDATE users SET password = %s WHERE username = %s',
                        (_hash_password(newPassword), username)
                    )
                conn.commit()
        except Exception:
            raise Exception(f"Error updating password for user {username} in database")

    def getSecuredUser(self, username: str):
        """Fetch one user as a SecuredUser (password hash excluded).

        Raises:
            Exception: wrapping any underlying database error.
        """
        try:
            with CommonDB.get_conn() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                    cursor.execute("SELECT * FROM users WHERE username = %s", (username,))
                    row = cursor.fetchone()
            return SecuredUser().setAll(row)
        except Exception:
            raise Exception("Error fetching user from database")

    def getAllUsers(self):
        """Fetch every user row as full User instances (including password hash).

        Raises:
            Exception: wrapping any underlying database error.
        """
        try:
            with CommonDB.get_conn() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                    cursor.execute("SELECT * FROM users")
                    rows = cursor.fetchall()
            return [User().setAll(row) for row in rows]
        except Exception:
            raise Exception("Error fetching users from database")

    def getAllSecuredUsers(self) -> dict:
        """Fetch every user as SecuredUser instances (password hash excluded),
        used to populate GlobalData.allUsers.

        Returns:
            dict mapping username to SecuredUser instance.

        Raises:
            Exception: wrapping any underlying database error.
        """
        try:
            with CommonDB.get_conn() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                    cursor.execute("SELECT * FROM users")
                    rows = cursor.fetchall()
            users = {}
            for row in rows:
                user = SecuredUser().setAll(row)
                users[user.getUsername()] = user
            return users
        except Exception:
            raise Exception("Error fetching users from database")

    def getAllUsernames(self):
        """Fetch the list of all usernames.

        Raises:
            Exception: wrapping any underlying database error.
        """
        try:
            with CommonDB.get_conn() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                    cursor.execute("SELECT username FROM users")
                    rows = cursor.fetchall()
            return [row['username'] for row in rows]
        except Exception:
            raise Exception("Error fetching usernames from database")

    def addUserFromDict(self, userDict: dict):
        """Insert a new user row from a plain dict, hashing its 'password'
        field if present.

        Returns:
            None on success, or the caught exception on failure.
        """
        try:
            userDict = dict(userDict)
            if userDict.get('password'):
                userDict['password'] = _hash_password(userDict['password'])
            with CommonDB.get_conn() as conn:
                CommonDB.addRecordFromDict(conn, 'users', userDict)
            return None
        except Exception as e:
            return e

    def updateUserFromDict(self, userDict: dict):
        """Update an existing user row (matched by 'username') from a plain
        dict, hashing 'password' if present, or leaving it untouched (popped
        from the update) if absent/falsy.

        Returns:
            None on success, or the caught exception on failure.
        """
        try:
            userDict = dict(userDict)
            if userDict.get('password'):
                userDict['password'] = _hash_password(userDict['password'])
            else:
                userDict.pop('password', None)
            with CommonDB.get_conn() as conn:
                CommonDB.updateRecordFromDict(conn, 'users', userDict, 'username')
            return None
        except Exception as e:
            return e

    def addUser(self, user: User):
        """Insert a new user row from a User object, hashing its password.

        Raises:
            Exception: if the username already exists, or on any DB error.
        """
        if self.isUsernameExists(user.getUsername()):
            raise Exception(f"Username {user.getUsername()} already exists")
        try:
            with CommonDB.get_conn() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                    cursor.execute(
                        'INSERT INTO users (username, password, name, role, department, email) VALUES (%s, %s, %s, %s, %s, %s)',
                        (user.getUsername(), _hash_password(user.getPassword()), user.getName(), user.getRole(), user.getDepartment(), user.getEmail())
                    )
                conn.commit()
        except Exception:
            raise Exception(f"Error adding user {user.getUsername()} to database")

    def updateUser(self, user: User):
        """Update password, name, department, email (and role, if set) for an
        existing user, matched by username.

        Raises:
            Exception: if the username doesn't exist, or on any DB error.
        """
        if not self.isUsernameExists(user.getUsername()):
            raise Exception(f"User {user.getUsername()} does not exist")
        try:
            with CommonDB.get_conn() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                    if user.getRole():
                        cursor.execute(
                            'UPDATE users SET password=%s, name=%s, department=%s, email=%s, role=%s WHERE username=%s',
                            (_hash_password(user.getPassword()), user.getName(), user.getDepartment(), user.getEmail(), user.getRole(), user.getUsername())
                        )
                    else:
                        cursor.execute(
                            'UPDATE users SET password=%s, name=%s, department=%s, email=%s WHERE username=%s',
                            (_hash_password(user.getPassword()), user.getName(), user.getDepartment(), user.getEmail(), user.getUsername())
                        )
                conn.commit()
        except Exception:
            raise Exception(f"Error updating user {user.getUsername()} in database")

    def updateTheme(self, username: str, theme: str | None):
        """Set (or clear, with None) the stored UI theme preference for a user.

        Raises:
            Exception: wrapping any underlying database error.
        """
        try:
            with CommonDB.get_conn() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("UPDATE users SET theme = %s WHERE username = %s", (theme, username))
                conn.commit()
        except Exception:
            raise Exception(f"Error updating theme for user {username}")

    def updateLanguage(self, username: str, language: str | None):
        """Set (or clear, with None) the stored UI language preference for a user.

        Raises:
            Exception: wrapping any underlying database error.
        """
        try:
            with CommonDB.get_conn() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("UPDATE users SET language = %s WHERE username = %s", (language, username))
                conn.commit()
        except Exception:
            raise Exception(f"Error updating language for user {username}")

    def setUserActive(self, username: str, is_active: bool):
        """Set the is_active flag for a user, controlling whether they can
        authenticate.

        Raises:
            Exception: if the username doesn't exist, or on any DB error.
        """
        if not self.isUsernameExists(username):
            raise Exception(f"User {username} does not exist")
        try:
            with CommonDB.get_conn() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("UPDATE users SET is_active = %s WHERE username = %s", (is_active, username))
                conn.commit()
        except Exception:
            raise Exception(f"Error updating active status for user {username}")

    def deleteUser(self, user: User):
        """Delete the user row matching user's username.

        Raises:
            Exception: if the username doesn't exist, or on any DB error.
        """
        if not self.isUsernameExists(user.getUsername()):
            raise Exception(f"User {user.getUsername()} does not exist")
        try:
            with CommonDB.get_conn() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                    cursor.execute("DELETE FROM users WHERE username = %s", (user.getUsername(),))
                conn.commit()
        except Exception:
            raise Exception(f"Error deleting user {user.getUsername()} from database")

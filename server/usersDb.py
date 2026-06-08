import secrets
import logging
import bcrypt
from psycopg2.extras import RealDictCursor

from User import User, UserRoles, SecuredUser
from commonDb import CommonDB


log = logging.getLogger(__name__)


def _hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()

def _verify_password(plain: str, hashed: str) -> bool:
    if not plain or not hashed:
        return False
    try:
        return bcrypt.checkpw(plain.encode(), hashed.encode())
    except Exception:
        return False


class UsersDb:
    def __init__(self):
        with CommonDB.get_conn() as conn:
            try:
                with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                    cursor.execute("""
                        CREATE TABLE IF NOT EXISTS users (
                            username VARCHAR(50) PRIMARY KEY,
                            password VARCHAR(100) NOT NULL,
                            name VARCHAR(100) NOT NULL,
                            role VARCHAR(50) NOT NULL,
                            department VARCHAR(100),
                            email VARCHAR(100),
                            ext VARCHAR(50),
                            theme VARCHAR(20)
                        )
                    """)
                    cursor.execute("SELECT COUNT(*) FROM users")
                    if cursor.fetchone()['count'] == 0:
                        seed_password = secrets.token_urlsafe(12)
                        cursor.execute('''
                            INSERT INTO users (username, password, name, role, department, email)
                            VALUES (%s, %s, %s, %s, %s, %s)''',
                            ("admin", _hash_password(seed_password), "Administrator", UserRoles.ADMIN, "Admin", "")
                        )
                        log.warning("=" * 60)
                        log.warning("INITIAL ADMIN PASSWORD: %s", seed_password)
                        log.warning("Change this immediately after first login.")
                        log.warning("=" * 60)
                conn.commit()
            except Exception as e:
                raise Exception("Error initializing users database: " + str(e))

    def isUsernameExists(self, username: str):
        try:
            with CommonDB.get_conn() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                    cursor.execute("SELECT username FROM users WHERE username = %s", (username,))
                    return cursor.fetchone() is not None
        except Exception:
            return False

    def getVerifiedUser(self, username: str, password: str) -> User | None:
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
        try:
            with CommonDB.get_conn() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                    cursor.execute("SELECT * FROM users WHERE username = %s", (username,))
                    row = cursor.fetchone()
            return SecuredUser().setAll(row)
        except Exception:
            raise Exception("Error fetching user from database")

    def getAllUsers(self):
        try:
            with CommonDB.get_conn() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                    cursor.execute("SELECT * FROM users")
                    rows = cursor.fetchall()
            return [User().setAll(row) for row in rows]
        except Exception:
            raise Exception("Error fetching users from database")

    def getAllSecuredUsers(self) -> dict:
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
        try:
            with CommonDB.get_conn() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                    cursor.execute("SELECT username FROM users")
                    rows = cursor.fetchall()
            return [row['username'] for row in rows]
        except Exception:
            raise Exception("Error fetching usernames from database")

    def addUserFromDict(self, userDict: dict):
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
        try:
            with CommonDB.get_conn() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("UPDATE users SET theme = %s WHERE username = %s", (theme, username))
                conn.commit()
        except Exception:
            raise Exception(f"Error updating theme for user {username}")

    def deleteUser(self, user: User):
        if not self.isUsernameExists(user.getUsername()):
            raise Exception(f"User {user.getUsername()} does not exist")
        try:
            with CommonDB.get_conn() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                    cursor.execute("DELETE FROM users WHERE username = %s", (user.getUsername(),))
                conn.commit()
        except Exception:
            raise Exception(f"Error deleting user {user.getUsername()} from database")

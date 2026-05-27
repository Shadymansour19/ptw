import os
import psycopg2
from psycopg2 import *
from psycopg2.extras import RealDictCursor

from User import User, UserRoles, SecuredUser
from commonDb import CommonDB

class UsersDb:
    def __init__(self):
        self.conn = psycopg2.connect(
            host=os.environ.get('DB_HOST', 'localhost'),
            database=os.environ.get('DB_NAME', 'ptw_database'),
            user=os.environ.get('DB_USER', 'postgres'),
            password=os.environ.get('DB_PASSWORD')
        )
        try:
            with self.conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS users (
                        username VARCHAR(50) PRIMARY KEY,
                        password VARCHAR(100) NOT NULL,
                        name VARCHAR(100) NOT NULL,
                        role VARCHAR(50) NOT NULL,
                        department VARCHAR(100),
                        email VARCHAR(100)
                    )
                """)
                cursor.execute("SELECT COUNT(*) FROM users")
                if cursor.fetchone()['count'] == 0:
                    cursor.execute('''
                        INSERT INTO users (username, password, name, role, department, email)
                        VALUES (%s, %s, %s, %s, %s, %s)''',
                        ("admin", "admin", "Administrator", UserRoles.ADMIN, "Admin", "")
                    )
            self.conn.commit()
        except Exception as e:
            self.conn.rollback()
            raise Exception("Error initializing users database: " + str(e))

    def isUsernameExists(self, username: str):
        try:
            with self.conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute("SELECT username FROM users WHERE username = %s", (username,))
                return cursor.fetchone() is not None
        except Exception as e:
            return False

    def updateUserPassword(self, username: str, newPassword: str):
        try:
            with self.conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute('''
                    UPDATE users
                    SET password = %s
                    WHERE username = %s''',
                    (newPassword, username)
                )
            self.conn.commit()
        except Exception as e:
            self.conn.rollback()
            raise Exception(f"Error updating password for user {username} in database")

    def getSecuredUser(self, username: str):
        try:
            with self.conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute("SELECT * FROM users WHERE username = %s", (username,))
                row = cursor.fetchone()
            return SecuredUser().setAll(row)
        except Exception as e:
            self.conn.rollback()
            raise Exception("Error fetching users from database")

    def getAllUsers(self):
        users = []
        try:
            with self.conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute("SELECT * FROM users")
                rows = cursor.fetchall()
            for row in rows:
                users.append(User().setAll(row))
        except Exception as e:
            self.conn.rollback()
            raise Exception("Error fetching users from database")
        return users

    def getAllSecuredUsers(self) -> dict[str, SecuredUser]:
        users = {}
        try:
            with self.conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute("SELECT * FROM users")
                rows = cursor.fetchall()
            for row in rows:
                user = SecuredUser().setAll(row)
                users[user.getUsername()] = user
        except Exception as e:
            self.conn.rollback()
            raise Exception("Error fetching users from database")
        return users

    def getAllUsernames(self):
        usernames = []
        try:
            with self.conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute("SELECT username FROM users")
                rows = cursor.fetchall()
            for row in rows:
                usernames.append(row['username'])
        except Exception as e:
            self.conn.rollback()
            raise Exception("Error fetching users from database")
        return usernames

    def addUserFromDict(self, userDict: dict):
        try:
            CommonDB.addRecordFromDict(self.conn, 'users', userDict)
            return None
        except Exception as e:
            return e

    def updateUserFromDict(self, userDict: dict):
        try:
            CommonDB.updateRecordFromDict(self.conn, 'users', userDict, 'username')
            return None
        except Exception as e:
            return e

    def addUser(self, user: User):
        if self.isUsernameExists(user.getUsername()):
            raise Exception(f"Username {user.getUsername()} already exists")

        try:
            with self.conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute('''
                    INSERT INTO users (username, password, name, role, department, email)
                    VALUES (%s, %s, %s, %s, %s, %s)''',
                    (user.getUsername(), user.getPassword(), user.getName(), user.getRole(), user.getDepartment(), user.getEmail())
                )
            self.conn.commit()
        except Exception as e:
            self.conn.rollback()
            raise Exception(f"Error adding user {user.getUsername()} to database")

    def updateUser(self, user: User):
        if not self.isUsernameExists(user.getUsername()):
            raise Exception(f"User {user.getUsername()} does not exist")

        try:
            varsToSet = f'''
                password = '{user.getPassword()}',
                name = '{user.getName()}',
                department = '{user.getDepartment()}',
                email = '{user.getEmail()}'
            '''
            if user.getRole():
                varsToSet += f", role = '{user.getRole()}'"

            with self.conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute('''
                    UPDATE users
                    SET ''' + varsToSet + '''
                    WHERE username = %s''',
                    (user.getUsername(),)
                )
            self.conn.commit()
        except Exception as e:
            self.conn.rollback()
            raise Exception(f"Error updating user {user.getUsername()} in database")

    def updateTheme(self, username: str, theme: str | None):
        try:
            with self.conn.cursor() as cursor:
                cursor.execute("UPDATE users SET theme = %s WHERE username = %s", (theme, username))
            self.conn.commit()
        except Exception as e:
            self.conn.rollback()
            raise Exception(f"Error updating theme for user {username}")

    def deleteUser(self, user: User):
        if not self.isUsernameExists(user.getUsername()):
            raise Exception(f"User {user.getUsername()} does not exist")

        try:
            with self.conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute("DELETE FROM users WHERE username = %s", (user.getUsername(),))
            self.conn.commit()
        except Exception as e:
            self.conn.rollback()
            raise Exception(f"Error deleting user {user.getUsername()} from database")

"""Small SQL boundary: the existing store's parameterized queries run on Postgres too."""

import re


class PostgresConnection:
    def __init__(self, connection):
        self.connection = connection

    @staticmethod
    def sql(statement):
        statement = re.sub(r"json_extract\(payload,\s*'\$\.mode'\)", "(payload::jsonb ->> 'mode')", statement)
        # Only application-owned SQL templates are translated, never parameter values.
        return statement.replace("?", "%s")

    def execute(self, statement, parameters=()):
        if statement == "BEGIN IMMEDIATE":
            statement = "SELECT 1"  # psycopg already opens the transaction
        return self.connection.execute(self.sql(statement), parameters)

    def executemany(self, statement, rows):
        cursor = self.connection.cursor()
        cursor.executemany(self.sql(statement), rows)
        return cursor

    def executescript(self, statement):
        return self.connection.execute(statement, prepare=False)

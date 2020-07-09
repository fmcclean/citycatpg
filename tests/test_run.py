from citycatpg import run
import psycopg2
from unittest import TestCase


class TestRun(TestCase):
    def test_add_run(self):
        con = psycopg2.connect(database='postgres', user='postgres', password='password', host='localhost')

        run.add_run(con, run_duration=500, srid=3035, resolution=90)

        with con.cursor() as cur:
            cur.execute('DROP TABLE runs')

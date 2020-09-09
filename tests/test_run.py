from citycatpg import Run, fetch
from unittest import TestCase
from .setup_tests import con
import datetime


class TestRun(TestCase):

    def test_add_run(self):
        with con:
            with con.cursor() as cur:
                cur.execute('DROP TABLE IF EXISTS runs')
        run = Run(run_duration=120, srid=3035, resolution=90, rain_total=100, rain_duration=120, run_name='test',
                  output_frequency=60)
        run.add(con)
        return run

    def test_fetch(self):
        with con:
            with con.cursor() as cur:
                cur.execute('DROP TABLE IF EXISTS runs')

        run = Run(run_duration=500, srid=3035, resolution=90)
        run.add(con)

        fetch(con, run_id=run.run_id)

    def test_generate_rainfall(self):
        run = Run(100, 3035, 90, rain_total=100, rain_duration=500)
        run.get_model(con)
        run.model.write('tests/test_model_generated')

    def test_get_model(self):
        run = Run(100, 3035, 90, rain_table='rain',
                  rain_start=datetime.datetime(2000, 1, 1), rain_end=datetime.datetime(2000, 1, 2))

        run.get_model(con)
        run.model.write('tests/test_model')

    def test_execute(self):
        run = Run(run_duration=120, srid=3035, resolution=90, rain_total=100, rain_duration=100, run_name='test',
                  output_frequency=60)
        run.get_model(con)
        run.execute('tests/test_model_execute', 'tests/test_model_execute')

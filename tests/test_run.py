from citycatpg import Run, fetch
from unittest import TestCase
from .setup_tests import con
import datetime


class TestRun(TestCase):

    def test_add_run(self):
        with con:
            with con.cursor() as cur:
                cur.execute('DROP TABLE IF EXISTS runs')
        run = Run(run_duration=120, rain_total=100, rain_duration=120, run_name='test',
                  output_frequency=60, domain_id=500, buildings_table='buildings')
        run.add(con)
        return run

    def test_fetch(self):
        with con:
            with con.cursor() as cur:
                cur.execute('DROP TABLE IF EXISTS runs')

        for run in [Run(rain_total=100, rain_duration=1800, run_duration=500, domain_id=500),
                    Run(rain_table='rain', run_duration=500, domain_id=500,
                        rain_start=datetime.datetime(2000, 1, 1), rain_end=datetime.datetime(2000, 1, 2))]:
            run.add(con)

            fetch(con, run_id=run.run_id).get_model(con)

    def test_generate_rainfall(self):
        run = Run(100, rain_total=100, rain_duration=500, domain_id=500)
        run.get_model(con)
        run.model.write('tests/test_model_generated')

    def test_get_model(self):
        run = Run(100, rain_table='rain',
                  rain_start=datetime.datetime(2000, 1, 1), rain_end=datetime.datetime(2000, 1, 2), domain_id=500,
                  buildings_table='buildings')

        run.get_model(con)
        run.model.write('tests/test_model')

    def test_execute(self):
        run = Run(run_duration=120, rain_total=100, rain_duration=100, run_name='test',
                  output_frequency=60, domain_id=500)
        run.get_model(con)
        run.execute('tests/test_model_execute', 'tests/test_model_execute')

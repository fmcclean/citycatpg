from citycatpg import server
from citycatpg.run import Run
from unittest import TestCase
import pika
import os
from .setup_tests import con


class TestServer(TestCase):

    def test_run_server(self):
        queue = 'test'
        connection = pika.BlockingConnection(pika.ConnectionParameters('localhost', port=5672))
        channel = connection.channel()
        channel.queue_declare(queue=queue)

        run = Run(run_duration=120, srid=3035, resolution=90, rain_total=100, rain_duration=120, run_name='test',
                  output_frequency=60, domain_id=500)
        run.add(con)

        channel.basic_publish(exchange='',
                              routing_key=queue,
                              body=run.run_id)
        server.run_server(queue=queue, con=con, run_path=os.path.abspath('tests/test_model_from_queue'),
                          out_path=os.path.abspath('tests/test_model_from_queue'), close=True)

from citycatpg import server
from unittest import TestCase
import pika
from .test_run import TestRun, con
import os


class TestServer(TestCase):

    def test_run_server(self):
        queue = 'test'
        connection = pika.BlockingConnection(pika.ConnectionParameters('localhost', port=5672))
        channel = connection.channel()
        channel.queue_declare(queue=queue)

        test_run = TestRun()
        run = test_run.test_add_run()

        channel.basic_publish(exchange='',
                              routing_key=queue,
                              body=run.run_id)
        server.run_server(queue=queue, con=con, run_path=os.path.abspath('tests/test_model_from_queue'),
                          out_path=os.path.abspath('tests/test_model_from_queue'), close=True)

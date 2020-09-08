from citycatpg import server
from unittest import TestCase
import pika


class TestServer(TestCase):

    def test_run_server(self):
        queue = 'test'
        connection = pika.BlockingConnection(pika.ConnectionParameters('localhost', port=5672))
        channel = connection.channel()
        channel.queue_declare(queue=queue)
        channel.basic_publish(exchange='',
                              routing_key=queue,
                              body='Hello World!')
        server.run_server(queue)

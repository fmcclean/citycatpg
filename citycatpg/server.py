import pika


def run_server():

    connection = pika.BlockingConnection(pika.ConnectionParameters('localhost', port=5672))
    channel = connection.channel()
    channel.queue_declare(queue='hello')
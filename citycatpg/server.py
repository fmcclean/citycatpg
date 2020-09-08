import pika


def callback(ch, method, properties, body):
    print(body)

    if method.routing_key == 'test':
        ch.close()


def run_server(queue='runs'):

    connection = pika.BlockingConnection(pika.ConnectionParameters('localhost', port=5672))
    channel = connection.channel()
    channel.basic_consume(queue=queue, auto_ack=True, on_message_callback=callback)
    channel.start_consuming()
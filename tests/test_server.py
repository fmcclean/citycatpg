from citycatpg import server
from unittest import TestCase


class TestServer(TestCase):

    def test_run_server(self):
        server.run_server()

from oioioi.base.tests import TestCase
from django.core.urlresolvers import reverse
from oioioi.workers import views


class TestServer(object):
    def get_workers(self):
        return [{'name': 'Komp4', 'tags': [], 'info': {
                    'concurrency': 2}}]


class TestWorkersInfo(TestCase):
    fixtures = ['test_users']

    def setUp(self):
        # monkeypatch test server instead of XMLRPC
        views.server = TestServer()

    def test_admin_can_see(self):
        self.client.login(username='test_admin')
        url = reverse('show_workers')
        response = self.client.get(url)
        self.assertIn('Komp4', response.content)

    def test_mundane_user_cant_see(self):
        self.client.login(username='test_user')
        url = reverse('show_workers')
        response = self.client.get(url)
        self.assertNotIn('Komp4', response.content)

from django.test import SimpleTestCase
from german_learning_api.api import api


class BotAuthOpenApiTests(SimpleTestCase):
    def test_bot_security_scheme_documents_both_required_headers(self):
        schema = api.get_openapi_schema()
        bot_scheme = schema["components"]["securitySchemes"]["BotAuth"]

        self.assertEqual(bot_scheme["name"], "X-API-Key")
        self.assertEqual(bot_scheme["in"], "header")
        self.assertIn("X-API-Key", bot_scheme["description"])
        self.assertIn("X-Telegram-ID", bot_scheme["description"])

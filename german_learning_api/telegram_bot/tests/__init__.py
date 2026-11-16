from unittest import TestSuite


def load_tests(loader, tests, pattern):
    suite = TestSuite()
    for module in (
        "test_onboarding",
        "test_browsing",
        "test_profile",
        "test_api_client",
        "test_word_addition",
        "test_word_deletion",
    ):
        suite.addTests(loader.loadTestsFromName(f"{__name__}.{module}"))
    return suite

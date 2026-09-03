from openai import OpenAI


def test_openai_responses_api_is_available():
    client = OpenAI(api_key="sk-test")
    assert hasattr(client, "responses")

import os
import groq
from groq import Groq


class Config(object):
    SECRET_KEY = os.environ.get('SECRET_KEY') or "secret_string"
    MONGO_URI = os.environ.get('MONGO_URI') or "mongodb://localhost:27017/Myhealth"
    api_key = "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"
    os.environ["GSK_API_KEY"] = api_key

    # Initialize the Groq client
    client = Groq(api_key=api_key)

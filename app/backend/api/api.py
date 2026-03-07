import logging
import os
from openai import OpenAI
from dotenv import load_dotenv


load_dotenv()
logger = logging.getLogger(__name__)

API_KEY = os.getenv("API_KEY")

client = OpenAI(
    api_key=API_KEY,
    base_url="https://api.siliconflow.com/v1",
)


async def llm_generation(prompt: str, user_id: str):
    try:
        response = client.images.generate(
            model="black-forest-labs/FLUX.1-schnell",
            prompt=prompt,
            size="256x256",
        )

        data = response.data[0]
        return data.url

    except Exception as err:
        logging.error(str(err)[:120])
        raise

import logging
import os
from openai import OpenAI
from dotenv import load_dotenv


load_dotenv()
logger = logging.getLogger(__name__)

API_KEY = os.getenv("API_KEY")
AI_MODEL = os.getenv("AI_MODEL")

client = OpenAI(
    api_key=API_KEY,
    base_url="https://openrouter.ai/api/v1",
)


async def llm_generation(prompt: str, user_id: str):
    if not prompt:
        return None

    try:
        response = client.chat.completions.create(
            model="nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free",
            messages=[
                {"role": "user", "content": prompt},
            ],
        )

        content = response.choices[0].message.content
        return content

    except Exception as err:
        logging.error(err)
        raise


if __name__ == "__main__":
    import asyncio

    prompt = "describe urself. can u create a pictures with format png, jpeg etc? or u only ascii model?)"
    response = asyncio.run(llm_generation(prompt, user_id="10"))

    print(response)

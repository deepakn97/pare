from __future__ import annotations

import litellm
from dotenv import load_dotenv


def main() -> None:
    # Load .env so OPENAI_API_KEY etc. are available.
    load_dotenv()

    try:
        response = litellm.completion(
            model="gpt-3.5-turbo", messages=[{"role": "user", "content": "ping"}], max_tokens=5
        )
    except Exception as error:  # pylint: disable=broad-except
        print("FAILED", error)
    else:
        content = response.choices[0].message.content if response.choices else ""
        print("SUCCESS", content)


if __name__ == "__main__":
    main()

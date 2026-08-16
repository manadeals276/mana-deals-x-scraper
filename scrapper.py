
import asyncio
import json
import os
import re
from pathlib import Path

from twikit import Client


SOURCES = [
    "Tech_glareOffl",
]

SEEN_FILE = Path("seen_posts.json")


def load_seen():
    if not SEEN_FILE.exists():
        return {}

    try:
        return json.loads(
            SEEN_FILE.read_text(encoding="utf-8")
        )
    except Exception:
        return {}


def save_seen(data):
    SEEN_FILE.write_text(
        json.dumps(data, indent=2),
        encoding="utf-8"
    )


def looks_like_deal(text):
    if not text:
        return False

    text_lower = text.lower()

    deal_words = [
        "₹",
        "rs.",
        "rs ",
        "inr",
        "% off",
        "off",
        "discount",
        "deal",
        "loot",
        "offer",
        "coupon",
        "cashback",
        "credit card",
        "debit card",
        "emi",
        "no cost",
        "amazon",
        "flipkart",
    ]

    return any(
        word in text_lower
        for word in deal_words
    )


def extract_urls(tweet):
    urls = []

    try:
        if getattr(tweet, "urls", None):
            urls.extend(tweet.urls)
    except Exception:
        pass

    text = getattr(tweet, "text", "") or ""

    urls.extend(
        re.findall(
            r"https?://[^\s]+",
            text
        )
    )

    # Remove duplicates while preserving order.
    result = []

    for url in urls:
        url = url.rstrip(
            ".,!?)]}"
        )

        if url not in result:
            result.append(url)

    return result


async def main():
    print("================================")
    print("MANA DEALS X COLLECTOR")
    print("================================")

    cookie_json = os.environ.get(
        "X_COOKIES_JSON"
    )

    if not cookie_json:
        raise RuntimeError(
            "X_COOKIES_JSON secret is missing."
        )

    cookies_path = Path(
        "cookies.json"
    )

    cookies_path.write_text(
        cookie_json,
        encoding="utf-8"
    )

    client = Client(
        language="en-US"
    )

    # Reuse the saved X cookies.
    client.load_cookies(
        str(cookies_path)
    )

    seen = load_seen()

    if not isinstance(seen, dict):
        seen = {}

    all_new_deals = []

    for username in SOURCES:

        print()
        print(
            f"Checking @{username}..."
        )

        try:
            user = await client.get_user_by_screen_name(
                username
            )

            print(
                f"User ID: {user.id}"
            )

            tweets = await client.get_user_tweets(
                user.id,
                "Tweets",
                count=20
            )

            previous_ids = set(
                seen.get(
                    username,
                    []
                )
            )

            current_ids = []

            for tweet in tweets:

                tweet_id = str(
                    tweet.id
                )

                current_ids.append(
                    tweet_id
                )

                if tweet_id in previous_ids:
                    continue

                text = (
                    getattr(
                        tweet,
                        "text",
                        ""
                    )
                    or ""
                ).strip()

                print(
                    f"NEW: {tweet_id}"
                )
                print(text[:250])

                if not looks_like_deal(
                    text
                ):
                    continue

                urls = extract_urls(
                    tweet
                )

                all_new_deals.append(
                    {
                        "source":
                            username,

                        "tweet_id":
                            tweet_id,

                        "text":
                            text,

                        "urls":
                            urls,

                        "created_at":
                            str(
                                getattr(
                                    tweet,
                                    "created_at",
                                    ""
                                )
                            ),

                        "tweet_url":
                            f"https://x.com/"
                            f"{username}/status/"
                            f"{tweet_id}",
                    }
                )

            # Keep last 100 IDs.
            merged = (
                current_ids
                + list(
                    previous_ids
                )
            )

            seen[username] = list(
                dict.fromkeys(
                    merged
                )
            )[:100]

        except Exception as error:

            print(
                f"ERROR @{username}: "
                f"{type(error).__name__}: "
                f"{error}"
            )

    save_seen(seen)

    print()
    print("================================")
    print(
        f"NEW DEALS FOUND: "
        f"{len(all_new_deals)}"
    )
    print("================================")

    for deal in all_new_deals:

        print()
        print(
            f"@{deal['source']}"
        )
        print(
            deal["text"]
        )

        if deal["urls"]:
            print(
                "URLs:"
            )

            for url in deal["urls"]:
                print(
                    f"  {url}"
                )

        print(
            f"Tweet: "
            f"{deal['tweet_url']}"
        )

    # Save output for the next workflow step.
    Path(
        "new_deals.json"
    ).write_text(
        json.dumps(
            all_new_deals,
            indent=2,
            ensure_ascii=False
        ),
        encoding="utf-8"
    )


if __name__ == "__main__":
    asyncio.run(
        main()
    )

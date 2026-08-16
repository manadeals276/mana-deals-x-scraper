import asyncio
import json
import os
import re
from pathlib import Path

from twikit import Client


# ============================================================
# MANA DEALS - X DEAL COLLECTOR
# ============================================================

SOURCES = [
    "dealztrendz",
    "Tech_glareOffl",
    "DealBeeOfficial",
]

SEEN_FILE = Path("seen_posts.json")
DEALS_FILE = Path("new_deals.json")


# ============================================================
# DEAL SIGNALS
# ============================================================

DEAL_SIGNALS = [
    "₹",
    "rs.",
    "rs ",
    "inr",
    "price",
    "off",
    "% off",
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
    "myntra",
    "croma",
    "reliance digital",
    "limited time",
    "sale",
    "save",
    "bank offer",
]


# ============================================================
# LOAD / SAVE SEEN POSTS
# ============================================================

def load_seen():
    if not SEEN_FILE.exists():
        return {}

    try:
        data = json.loads(
            SEEN_FILE.read_text(
                encoding="utf-8"
            )
        )

        if isinstance(data, dict):
            return data

        return {}

    except Exception as error:
        print(
            f"Warning: could not load seen_posts.json: {error}"
        )
        return {}


def save_seen(data):
    SEEN_FILE.write_text(
        json.dumps(
            data,
            indent=2,
            ensure_ascii=False
        ),
        encoding="utf-8"
    )


# ============================================================
# DEAL DETECTION
# ============================================================

def looks_like_deal(text):
    if not text:
        return False

    text_lower = text.lower()

    matches = 0

    for signal in DEAL_SIGNALS:
        if signal in text_lower:
            matches += 1

    # At least one strong deal signal.
    return matches >= 1


# ============================================================
# EXTRACT URLS
# ============================================================

def extract_urls(tweet):

    urls = []

    # --------------------------------------------------------
    # 1. Twifork/Twikit URL objects
    # --------------------------------------------------------

    try:

        tweet_urls = getattr(
            tweet,
            "urls",
            None
        )

        if tweet_urls:

            for item in tweet_urls:

                url = None

                # URL returned as normal string
                if isinstance(
                    item,
                    str
                ):
                    url = item

                # URL returned as dictionary
                elif isinstance(
                    item,
                    dict
                ):

                    url = (
                        item.get(
                            "expanded_url"
                        )
                        or item.get(
                            "url"
                        )
                        or item.get(
                            "display_url"
                        )
                    )

                # Unknown object
                else:

                    try:
                        url = getattr(
                            item,
                            "expanded_url",
                            None
                        )

                        if not url:
                            url = getattr(
                                item,
                                "url",
                                None
                            )

                    except Exception:
                        url = None

                if url:
                    urls.append(
                        str(url)
                    )

    except Exception as error:

        print(
            f"URL extraction warning: {error}"
        )

    # --------------------------------------------------------
    # 2. Extract URLs directly from tweet text
    # --------------------------------------------------------

    text = (
        getattr(
            tweet,
            "text",
            ""
        )
        or ""
    )

    text_urls = re.findall(
        r"https?://[^\s]+",
        text
    )

    urls.extend(
        text_urls
    )

    # --------------------------------------------------------
    # 3. Clean and deduplicate
    # --------------------------------------------------------

    cleaned = []

    for url in urls:

        if not url:
            continue

        url = str(
            url
        ).strip()

        url = url.rstrip(
            ".,!?)]}>\"'"
        )

        if (
            url
            and url not in cleaned
        ):
            cleaned.append(
                url
            )

    return cleaned


# ============================================================
# GET TWEET TEXT
# ============================================================

def get_tweet_text(tweet):

    try:

        text = getattr(
            tweet,
            "text",
            ""
        )

        if text is None:
            return ""

        return str(
            text
        ).strip()

    except Exception:
        return ""


# ============================================================
# GET TWEET ID
# ============================================================

def get_tweet_id(tweet):

    try:

        tweet_id = getattr(
            tweet,
            "id",
            None
        )

        if tweet_id is None:
            return None

        return str(
            tweet_id
        )

    except Exception:
        return None


# ============================================================
# GET TWEET DATE
# ============================================================

def get_tweet_date(tweet):

    try:

        value = getattr(
            tweet,
            "created_at",
            ""
        )

        if value is None:
            return ""

        return str(
            value
        )

    except Exception:
        return ""


# ============================================================
# PROCESS ONE ACCOUNT
# ============================================================

async def process_account(
    client,
    username,
    seen
):

    print()
    print(
        "================================"
    )

    print(
        f"Checking @{username}..."
    )

    print(
        "================================"
    )

    previous_ids = set(
        str(x)
        for x in seen.get(
            username,
            []
        )
    )

    current_ids = []

    new_deals = []

    try:

        # ----------------------------------------------------
        # Find X user
        # ----------------------------------------------------

        user = await client.get_user_by_screen_name(
            username
        )

        print(
            f"User ID: {user.id}"
        )

        # ----------------------------------------------------
        # Fetch recent posts
        # ----------------------------------------------------

        tweets = await client.get_user_tweets(
            user.id,
            "Tweets",
            count=20
        )

        # ----------------------------------------------------
        # Process posts
        # ----------------------------------------------------

        for tweet in tweets:

            tweet_id = get_tweet_id(
                tweet
            )

            if not tweet_id:
                continue

            current_ids.append(
                tweet_id
            )

            # Already processed
            if tweet_id in previous_ids:
                continue

            text = get_tweet_text(
                tweet
            )

            print()
            print(
                f"NEW: {tweet_id}"
            )

            print(
                text[:500]
            )

            # ------------------------------------------------
            # Deal filtering
            # ------------------------------------------------

            if not looks_like_deal(
                text
            ):

                print(
                    "Not classified as a deal."
                )

                continue

            # ------------------------------------------------
            # URLs
            # ------------------------------------------------

            urls = extract_urls(
                tweet
            )

            tweet_url = (
                f"https://x.com/"
                f"{username}/status/"
                f"{tweet_id}"
            )

            deal = {
                "source": username,

                "tweet_id": tweet_id,

                "tweet_url": tweet_url,

                "text": text,

                "urls": urls,

                "created_at":
                    get_tweet_date(
                        tweet
                    ),
            }

            new_deals.append(
                deal
            )

            print()
            print(
                "DEAL DETECTED:"
            )

            print(
                text[:500]
            )

            if urls:

                print(
                    "URLs:"
                )

                for url in urls:

                    print(
                        f"  {url}"
                    )

            else:

                print(
                    "URLs: none"
                )

        # ----------------------------------------------------
        # Update seen IDs
        # ----------------------------------------------------

        merged = (
            current_ids
            + list(
                previous_ids
            )
        )

        # Keep only latest 100 IDs
        seen[username] = list(
            dict.fromkeys(
                merged
            )
        )[:100]

        print()
        print(
            f"@{username}: "
            f"{len(new_deals)} new deal(s)"
        )

        return new_deals

    except Exception as error:

        print()
        print(
            f"ERROR @{username}: "
            f"{type(error).__name__}: "
            f"{error}"
        )

        # Keep existing seen IDs.
        if username not in seen:
            seen[username] = []

        return []


# ============================================================
# MAIN
# ============================================================

async def main():

    print()
    print(
        "================================"
    )

    print(
        "MANA DEALS X COLLECTOR"
    )

    print(
        "================================"
    )

    # --------------------------------------------------------
    # X cookies
    # --------------------------------------------------------

    cookie_json = os.environ.get(
        "X_COOKIES_JSON"
    )

    if not cookie_json:

        raise RuntimeError(
            "X_COOKIES_JSON GitHub secret is missing."
        )

    # --------------------------------------------------------
    # Create temporary cookie file
    # --------------------------------------------------------

    cookies_path = Path(
        "cookies.json"
    )

    try:

        # Validate JSON first
        cookies = json.loads(
            cookie_json
        )

        if not isinstance(
            cookies,
            dict
        ):

            raise ValueError(
                "X_COOKIES_JSON must contain a JSON object."
            )

        cookies_path.write_text(
            json.dumps(
                cookies
            ),
            encoding="utf-8"
        )

    except Exception as error:

        raise RuntimeError(
            "X_COOKIES_JSON is not valid JSON: "
            f"{error}"
        )

    # --------------------------------------------------------
    # Twifork/Twikit client
    # --------------------------------------------------------

    client = Client(
        language="en-US"
    )

    # Load existing X session cookies.
    client.load_cookies(
        str(
            cookies_path
        )
    )

    # --------------------------------------------------------
    # Load state
    # --------------------------------------------------------

    seen = load_seen()

    all_new_deals = []

    # --------------------------------------------------------
    # Process all sources
    # --------------------------------------------------------

    for username in SOURCES:

        deals = await process_account(
            client,
            username,
            seen
        )

        all_new_deals.extend(
            deals
        )

    # --------------------------------------------------------
    # Save seen IDs
    # --------------------------------------------------------

    save_seen(
        seen
    )

    # --------------------------------------------------------
    # Save new deals
    # --------------------------------------------------------

    DEALS_FILE.write_text(
        json.dumps(
            all_new_deals,
            indent=2,
            ensure_ascii=False
        ),
        encoding="utf-8"
    )

    # --------------------------------------------------------
    # Final output
    # --------------------------------------------------------

    print()
    print(
        "================================"
    )

    print(
        f"NEW DEALS FOUND: "
        f"{len(all_new_deals)}"
    )

    print(
        "================================"
    )

    for index, deal in enumerate(
        all_new_deals,
        start=1
    ):

        print()
        print(
            f"{index}. "
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

    print()
    print(
        "Collector finished successfully."
    )


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":

    asyncio.run(
        main()
    )

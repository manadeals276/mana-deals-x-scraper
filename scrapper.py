import asyncio
import json
import os
import re
from pathlib import Path
from urllib.request import Request, urlopen

from twikit import Client


# ============================================================
# MANA DEALS X COLLECTOR
# ============================================================

SOURCES = {
    "dealztrendz": "1045737414625382400",
    "Tech_glareOffl": "1196118601415053314",
    "DealBeeOfficial": "2923571768",
}

TWEETS_PER_ACCOUNT = 20
MAX_DEALS_PER_ACCOUNT = 5

SEEN_FILE = Path("seen_posts.json")
DEALS_FILE = Path("new_deals.json")


# ============================================================
# DEAL SIGNALS
# ============================================================

DEAL_WORDS = [
    "deal",
    "loot",
    "offer",
    "discount",
    "coupon",
    "cashback",
    "sale",
    "off",
    "save",
    "price drop",
    "bank offer",
    "credit card",
    "debit card",
    "emi",
    "no cost",
    "limited time",
    "lowest",
    "best price",
]

STORE_WORDS = [
    "amazon",
    "flipkart",
    "myntra",
    "croma",
    "ajio",
    "meesho",
    "nykaa",
    "tatacliq",
    "reliance digital",
    "vijay sales",
]


# ============================================================
# LOAD SEEN POSTS
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

    except Exception as error:
        print(
            f"Warning: could not load seen_posts.json: {error}"
        )

    return {}


# ============================================================
# SAVE SEEN POSTS
# ============================================================

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
# SAFE ATTRIBUTE
# ============================================================

def safe_attr(obj, name, default=None):
    try:
        value = getattr(
            obj,
            name,
            default
        )

        if value is None:
            return default

        return value

    except Exception:
        return default


# ============================================================
# GET TWEET TEXT
# ============================================================

def get_tweet_text(tweet):

    text = safe_attr(
        tweet,
        "text",
        ""
    )

    return str(
        text or ""
    ).strip()


# ============================================================
# GET TWEET ID
# ============================================================

def get_tweet_id(tweet):

    tweet_id = safe_attr(
        tweet,
        "id",
        None
    )

    if tweet_id is None:
        return None

    return str(
        tweet_id
    )


# ============================================================
# EXTRACT URLS
# ============================================================

def extract_urls(tweet):

    text = get_tweet_text(
        tweet
    )

    urls = []

    # --------------------------------------------------------
    # URLs directly present in tweet text
    # --------------------------------------------------------

    text_urls = re.findall(
        r"https?://[^\s<>\"]+",
        text
    )

    urls.extend(
        text_urls
    )

    # --------------------------------------------------------
    # Twikit URL objects, if available
    # --------------------------------------------------------

    try:

        tweet_urls = safe_attr(
            tweet,
            "urls",
            []
        )

        if tweet_urls:

            for item in tweet_urls:

                url = None

                if isinstance(
                    item,
                    str
                ):

                    url = item

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
                    )

                else:

                    url = (
                        safe_attr(
                            item,
                            "expanded_url",
                            None
                        )
                        or safe_attr(
                            item,
                            "url",
                            None
                        )
                    )

                if url:
                    urls.append(
                        str(url)
                    )

    except Exception:
        pass

    # --------------------------------------------------------
    # Clean + deduplicate
    # --------------------------------------------------------

    cleaned = []

    for url in urls:

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
# BASIC DEAL FILTER
# ============================================================

def looks_like_candidate(
    text,
    urls
):

    if not text:
        return False

    lower = text.lower()

    # --------------------------------------------------------
    # Ignore retweets
    # --------------------------------------------------------

    if lower.startswith(
        "rt @"
    ):
        return False

    # --------------------------------------------------------
    # Ignore obvious replies
    # --------------------------------------------------------

    if lower.startswith("@"):
        return False

    # --------------------------------------------------------
    # Must have URL
    # --------------------------------------------------------

    if not urls:
        return False

    # --------------------------------------------------------
    # Price
    # --------------------------------------------------------

    has_rupee = (
        "₹" in text
        or bool(
            re.search(
                r"\brs\.?\s*\d",
                lower
            )
        )
        or bool(
            re.search(
                r"\binr\s*\d",
                lower
            )
        )
    )

    # --------------------------------------------------------
    # Percentage
    # --------------------------------------------------------

    has_percentage = bool(
        re.search(
            r"\b\d{1,3}\s*%\s*(off|discount)?",
            lower
        )
    )

    # --------------------------------------------------------
    # Deal words
    # --------------------------------------------------------

    has_deal_word = any(
        word in lower
        for word in DEAL_WORDS
    )

    # --------------------------------------------------------
    # Store
    # --------------------------------------------------------

    has_store = any(
        store in lower
        for store in STORE_WORDS
    )

    # --------------------------------------------------------
    # Strong enough candidate
    # --------------------------------------------------------

    if has_rupee:
        return True

    if has_percentage and (
        has_deal_word
        or has_store
    ):
        return True

    if has_deal_word and has_store:
        return True

    return False


# ============================================================
# SEND TO CLOUDFLARE WORKER
# ============================================================

async def send_to_worker(deal):

    worker_url = os.environ.get(
        "MANA_WORKER_URL"
    )

    if not worker_url:

        print(
            "ERROR: MANA_WORKER_URL is missing."
        )

        return False

    payload = {
        "source": deal["source"],
        "tweet_id": deal["tweet_id"],
        "tweet_url": deal["tweet_url"],
        "text": deal["text"],
        "urls": deal["urls"],
    }

    body = json.dumps(
        payload,
        ensure_ascii=False
    ).encode(
        "utf-8"
    )

    request = Request(
        worker_url,
        data=body,
        headers={
            "Content-Type":
                "application/json",

            "User-Agent":
                "ManaDeals-X-Collector/1.0",
        },
        method="POST"
    )

    print()
    print(
        "Sending deal to Cloudflare Worker..."
    )

    print(
        f"Source: @{deal['source']}"
    )

    print(
        f"Tweet ID: {deal['tweet_id']}"
    )

    try:

        response = await asyncio.to_thread(
            urlopen,
            request,
            timeout=30
        )

        response_body = (
            response
            .read()
            .decode(
                "utf-8",
                errors="replace"
            )
        )

        print(
            f"Worker HTTP status: "
            f"{response.status}"
        )

        print(
            f"Worker response: "
            f"{response_body[:1000]}"
        )

        return (
            200 <= response.status < 300
        )

    except Exception as error:

        print(
            "Worker request failed:"
        )

        print(
            f"{type(error).__name__}: {error}"
        )

        return False


# ============================================================
# PROCESS ONE X ACCOUNT
# ============================================================

async def process_account(
    client,
    username,
    user_id,
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

    print(
        f"User ID: {user_id}"
    )

    previous_ids = set(
        str(x)
        for x in seen.get(
            username,
            []
        )
    )

    current_ids = []

    candidates = []

    try:

        # ----------------------------------------------------
        # IMPORTANT:
        # Fetch directly using USER ID.
        #
        # This avoids get_user_by_screen_name()
        # and avoids unnecessary User parsing.
        # ----------------------------------------------------

        tweets = await client.get_user_tweets(
            user_id,
            "Tweets",
            count=TWEETS_PER_ACCOUNT
        )

        # ----------------------------------------------------
        # Process tweets
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

            urls = extract_urls(
                tweet
            )

            # ------------------------------------------------
            # Filter
            # ------------------------------------------------

            if not looks_like_candidate(
                text,
                urls
            ):

                print(
                    "Not classified as a deal."
                )

                continue

            tweet_url = (
                f"https://x.com/"
                f"{username}/status/"
                f"{tweet_id}"
            )

            deal = {
                "source":
                    username,

                "tweet_id":
                    tweet_id,

                "tweet_url":
                    tweet_url,

                "text":
                    text,

                "urls":
                    urls,
            }

            candidates.append(
                deal
            )

            print()
            print(
                "DEAL CANDIDATE:"
            )

            print(
                text[:500]
            )

            print(
                "URLs:"
            )

            for url in urls:

                print(
                    f"  {url}"
                )

            if (
                len(candidates)
                >= MAX_DEALS_PER_ACCOUNT
            ):
                break

        # ----------------------------------------------------
        # Save IDs
        # ----------------------------------------------------

        merged_ids = (
            current_ids
            + list(previous_ids)
        )

        seen[username] = list(
            dict.fromkeys(
                merged_ids
            )
        )[:100]

        print()
        print(
            f"@{username}: "
            f"{len(candidates)} "
            f"candidate(s)"
        )

        return candidates

    except Exception as error:

        print()
        print(
            f"ERROR @{username}: "
            f"{type(error).__name__}: "
            f"{error}"
        )

        # Don't destroy existing state
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
    # Worker
    # --------------------------------------------------------

    worker_url = os.environ.get(
        "MANA_WORKER_URL"
    )

    if not worker_url:

        raise RuntimeError(
            "MANA_WORKER_URL GitHub secret is missing."
        )

    print(
        "Cloudflare Worker:"
    )

    print(
        "***"
    )

    # --------------------------------------------------------
    # X Cookies
    # --------------------------------------------------------

    cookie_json = os.environ.get(
        "X_COOKIES_JSON"
    )

    if not cookie_json:

        raise RuntimeError(
            "X_COOKIES_JSON GitHub secret is missing."
        )

    try:

        cookies = json.loads(
            cookie_json
        )

        if not isinstance(
            cookies,
            dict
        ):

            raise ValueError(
                "X_COOKIES_JSON must be a JSON object."
            )

    except Exception as error:

        raise RuntimeError(
            f"Invalid X_COOKIES_JSON: {error}"
        )

    cookies_path = Path(
        "cookies.json"
    )

    cookies_path.write_text(
        json.dumps(
            cookies
        ),
        encoding="utf-8"
    )

    # --------------------------------------------------------
    # Twikit client
    # --------------------------------------------------------

    client = Client(
        language="en-US"
    )

    # --------------------------------------------------------
    # Load cookies
    # --------------------------------------------------------

    client.load_cookies(
        str(
            cookies_path
        )
    )

    # --------------------------------------------------------
    # State
    # --------------------------------------------------------

    seen = load_seen()

    all_candidates = []

    # --------------------------------------------------------
    # Scrape accounts
    # --------------------------------------------------------

    for username, user_id in SOURCES.items():

        deals = await process_account(
            client,
            username,
            user_id,
            seen
        )

        all_candidates.extend(
            deals
        )

    # --------------------------------------------------------
    # Save new deals
    # --------------------------------------------------------

    DEALS_FILE.write_text(
        json.dumps(
            all_candidates,
            indent=2,
            ensure_ascii=False
        ),
        encoding="utf-8"
    )

    # --------------------------------------------------------
    # Send to Worker
    # --------------------------------------------------------

    sent_count = 0
    failed_count = 0

    print()
    print(
        "================================"
    )

    print(
        f"TOTAL NEW CANDIDATES: "
        f"{len(all_candidates)}"
    )

    print(
        "================================"
    )

    for deal in all_candidates:

        success = await send_to_worker(
            deal
        )

        if success:
            sent_count += 1
        else:
            failed_count += 1

    # --------------------------------------------------------
    # Save state
    # --------------------------------------------------------

    save_seen(
        seen
    )

    # --------------------------------------------------------
    # Final
    # --------------------------------------------------------

    print()
    print(
        "================================"
    )

    print(
        "COLLECTOR FINISHED"
    )

    print(
        "================================"
    )

    print(
        f"New candidates: {len(all_candidates)}"
    )

    print(
        f"Sent to Worker: {sent_count}"
    )

    print(
        f"Worker failures: {failed_count}"
    )

    print(
        "================================"
    )


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":

    asyncio.run(
        main()
    )

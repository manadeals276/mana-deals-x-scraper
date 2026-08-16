import asyncio
import json
import os
import re
from pathlib import Path

from twikit import Client


# ============================================================
# MANA DEALS X SCRAPER
# ============================================================

SOURCES = [
    "dealztrendz",
    "Tech_glareOffl",
    "DealBeeOfficial",
]

SEEN_FILE = Path("seen_posts.json")
DEALS_FILE = Path("new_deals.json")

# Maximum candidates sent to Cloudflare from each account
MAX_DEALS_PER_ACCOUNT = 5

# Maximum recent tweets checked per account
TWEETS_PER_ACCOUNT = 20


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
    "price",
    "off",
    "save",
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

        return {}

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
# GET TWEET TEXT
# ============================================================

def get_tweet_text(tweet):

    try:

        return str(
            getattr(
                tweet,
                "text",
                ""
            ) or ""
        ).strip()

    except Exception:

        return ""


# ============================================================
# GET TWEET ID
# ============================================================

def get_tweet_id(tweet):

    try:

        value = getattr(
            tweet,
            "id",
            None
        )

        if value is None:
            return None

        return str(value)

    except Exception:

        return None


# ============================================================
# GET TWEET DATE
# ============================================================

def get_tweet_date(tweet):

    try:

        return str(
            getattr(
                tweet,
                "created_at",
                ""
            ) or ""
        )

    except Exception:

        return ""


# ============================================================
# URL EXTRACTION
# ============================================================

def extract_urls(tweet):

    urls = []

    # --------------------------------------------------------
    # URLs supplied by Twifork
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
                        or item.get(
                            "display_url"
                        )
                    )

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
            f"URL object warning: {error}"
        )

    # --------------------------------------------------------
    # URLs directly inside tweet text
    # --------------------------------------------------------

    text = get_tweet_text(
        tweet
    )

    text_urls = re.findall(
        r"https?://[^\s<>\"]+",
        text
    )

    urls.extend(
        text_urls
    )

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
# REMOVE TWITTER SHORT LINKS DUPLICATES
# ============================================================

def clean_urls(urls):

    result = []

    for url in urls:

        if not url:
            continue

        url = str(
            url
        ).strip()

        if url not in result:

            result.append(
                url
            )

    return result


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

    if lower.startswith(
        "@"
    ):

        return False

    # --------------------------------------------------------
    # Must have a shopping/offer URL
    # --------------------------------------------------------

    if not urls:

        return False

    # --------------------------------------------------------
    # Price indicators
    # --------------------------------------------------------

    has_rupee = (
        "₹" in text
        or "rs." in lower
        or "rs " in lower
        or "inr" in lower
    )

    # --------------------------------------------------------
    # Percentage discount
    # --------------------------------------------------------

    has_percentage = bool(
        re.search(
            r"\b\d{1,3}\s*%\s*(off|discount)?\b",
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
    # Store mention
    # --------------------------------------------------------

    has_store = any(
        store in lower
        for store in STORE_WORDS
    )

    # --------------------------------------------------------
    # Product-looking content
    #
    # We don't require every deal to have a price because
    # the Cloudflare AI layer can process bank/coupon offers.
    # --------------------------------------------------------

    has_product_signal = (
        has_rupee
        or has_percentage
        or has_store
    )

    # --------------------------------------------------------
    # Strong candidate
    # --------------------------------------------------------

    if has_product_signal and (
        has_deal_word
        or has_rupee
        or has_percentage
        or has_store
    ):

        return True

    return False


# ============================================================
# SEND DEAL TO CLOUDFLARE WORKER
# ============================================================

async def send_to_worker(
    deal
):

    worker_url = os.environ.get(
        "MANA_WORKER_URL"
    )

    if not worker_url:

        raise RuntimeError(
            "MANA_WORKER_URL GitHub secret is missing."
        )

    payload = {
        "source": deal["source"],

        "tweet_id": deal["tweet_id"],

        "tweet_url": deal["tweet_url"],

        "text": deal["text"],

        "urls": deal["urls"],
    }

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

        import urllib.request

        body = json.dumps(
            payload,
            ensure_ascii=False
        ).encode(
            "utf-8"
        )

        request = urllib.request.Request(
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

        # Run blocking urllib in a thread
        # so the async scraper isn't blocked.

        response = await asyncio.to_thread(
            urllib.request.urlopen,
            request,
            timeout=30
        )

        response_body = (
            response.read()
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

        return True

    except Exception as error:

        print()
        print(
            "Worker request failed:"
        )

        print(
            f"{type(error).__name__}: "
            f"{error}"
        )

        return False


# ============================================================
# PROCESS ACCOUNT
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

    candidates = []

    try:

        # ----------------------------------------------------
        # GET USER
        # ----------------------------------------------------

        user = await client.get_user_by_screen_name(
            username
        )

        print(
            f"User ID: {user.id}"
        )

        # ----------------------------------------------------
        # GET RECENT POSTS
        # ----------------------------------------------------

        tweets = await client.get_user_tweets(
            user.id,
            "Tweets",
            count=TWEETS_PER_ACCOUNT
        )

        # ----------------------------------------------------
        # PROCESS POSTS
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
                text[:400]
            )

            # ------------------------------------------------
            # URLs
            # ------------------------------------------------

            urls = clean_urls(
                extract_urls(
                    tweet
                )
            )

            # ------------------------------------------------
            # Candidate filter
            # ------------------------------------------------

            if not looks_like_candidate(
                text,
                urls
            ):

                print(
                    "Not a strong deal candidate."
                )

                continue

            tweet_url = (
                "https://x.com/"
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

                "created_at":
                    get_tweet_date(
                        tweet
                    ),

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

            # Don't collect unlimited candidates
            if len(candidates) >= MAX_DEALS_PER_ACCOUNT:

                break

        # ----------------------------------------------------
        # Update seen IDs
        # ----------------------------------------------------

        merged_ids = (
            current_ids
            + list(
                previous_ids
            )
        )

        # Keep last 100 tweet IDs
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
    # CHECK WORKER URL
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
        worker_url
    )

    # --------------------------------------------------------
    # CHECK X COOKIES
    # --------------------------------------------------------

    cookie_json = os.environ.get(
        "X_COOKIES_JSON"
    )

    if not cookie_json:

        raise RuntimeError(
            "X_COOKIES_JSON GitHub secret is missing."
        )

    # --------------------------------------------------------
    # Validate cookies JSON
    # --------------------------------------------------------

    cookies_path = Path(
        "cookies.json"
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

        cookies_path.write_text(
            json.dumps(
                cookies
            ),
            encoding="utf-8"
        )

    except Exception as error:

        raise RuntimeError(
            "Invalid X_COOKIES_JSON: "
            f"{error}"
        )

    # --------------------------------------------------------
    # Create Twifork client
    # --------------------------------------------------------

    client = Client(
        language="en-US"
    )

    # --------------------------------------------------------
    # Load X cookies
    # --------------------------------------------------------

    client.load_cookies(
        str(
            cookies_path
        )
    )

    # --------------------------------------------------------
    # Load state
    # --------------------------------------------------------

    seen = load_seen()

    all_candidates = []

    # --------------------------------------------------------
    # SCRAPE ALL SOURCES
    # --------------------------------------------------------

    for username in SOURCES:

        deals = await process_account(
            client,
            username,
            seen
        )

        all_candidates.extend(
            deals
        )

    # --------------------------------------------------------
    # SAVE LOCAL DEAL DATA
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
    # SEND CANDIDATES TO WORKER
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
    # SAVE SEEN STATE
    # --------------------------------------------------------

    save_seen(
        seen
    )

    # --------------------------------------------------------
    # FINAL RESULT
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
        f"New candidates: "
        f"{len(all_candidates)}"
    )

    print(
        f"Sent to Worker: "
        f"{sent_count}"
    )

    print(
        f"Worker failures: "
        f"{failed_count}"
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

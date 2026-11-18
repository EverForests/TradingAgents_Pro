"""Sentiment analyst: one sentiment report from three sources.

The node fetches its sources before calling the model and puts them in the
prompt, so the model reports on data it was given rather than inventing posts:

  1. News headlines: Yahoo Finance
  2. StockTwits messages: the cashtag stream, with Bullish/Bearish tags
  3. Reddit posts: r/wallstreetbets, r/stocks, r/investing, or crypto communities for a crypto pair

Each source is trimmed to the analysis window. With a TypeSafe key, the social
posts are screened by Jev first (see post_screen). These feeds serve recent items
and are not archived, so a historical run's sentiment inputs are not
point-in-time.

The report is a SentimentReport through structured output where the provider
supports it and free text otherwise, so the band, score and confidence header
reads the same across providers.
"""

import json
import logging
import re
from datetime import datetime, timedelta

from langchain_core.messages import AIMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from tradingagents.agents import sentiment_coverage
from tradingagents.agents.context import get_instrument_context_from_state, get_language_instruction
from tradingagents.agents.post_screen import jev_screen
from tradingagents.agents.schemas import SentimentReport, render_sentiment_assessment
from tradingagents.agents.state import new_course_run
from tradingagents.agents.structured import (
    NO_EXTERNAL_TOOLS,
    bind_structured,
    invoke_structured,
)
from tradingagents.agents.tools import get_news
from tradingagents.dataflows.source_receipt import SourceReceipt, SourceText
from tradingagents.dataflows.symbols import normalize_symbol
from tradingagents.dataflows.vendors.reddit import (
    CRYPTO_SUBREDDITS,
    DEFAULT_SUBREDDITS,
    fetch_reddit_posts,
    subreddits_for,
)
from tradingagents.dataflows.vendors.stocktwits import fetch_stocktwits_messages

logger = logging.getLogger(__name__)


def _seven_days_back(trade_date: str) -> str:
    return (datetime.strptime(trade_date, "%Y-%m-%d") - timedelta(days=7)).strftime("%Y-%m-%d")


def create_sentiment_analyst(llm):
    """Create a sentiment analyst node for the trading graph.

    Pre-fetches news + StockTwits + Reddit data with collection receipts,
    normalizes each source against the run's identity and window, and lets the
    model read only validated content. Coverage is decided before the model is
    consulted: with zero valid sources the node skips the model entirely and
    emits a deterministic UNKNOWN/null record. The legacy ``sentiment_report``
    string and the message are rendered from the same assessment record.
    """
    structured_llm = None
    structured_bound = False

    def sentiment_analyst_node(state):
        nonlocal structured_llm, structured_bound

        ticker = state["company_of_interest"]
        end_date = state["trade_date"]
        start_date = _seven_days_back(end_date)
        instrument_context = get_instrument_context_from_state(state)
        run = _course_run_for(state, ticker, end_date)

        news_block, stocktwits_block, reddit_block, subreddits = _collect_sources(
            state, run, ticker, start_date, end_date
        )

        sources = {
            source_id: sentiment_coverage.normalize_source(
                block, source_id, run, start_date, end_date
            )
            for source_id, block in (
                ("news", news_block),
                ("stocktwits", stocktwits_block),
                ("reddit", reddit_block),
            )
        }
        coverage = sentiment_coverage.build_sentiment_coverage(list(sources.values()), run)

        assessment = None
        if coverage["valid_sources"] > 0:
            # Only validated content reaches the prompt: a raw placeholder or an
            # opaque string is left out rather than inviting the model to read it.
            def shown(source_id, block):
                return str(block) if coverage["sources"][source_id]["available"] else ""

            system_message = _build_system_message(
                ticker=ticker,
                start_date=start_date,
                end_date=end_date,
                news_block=shown("news", news_block),
                stocktwits_block=shown("stocktwits", stocktwits_block),
                reddit_block=shown("reddit", reddit_block),
                subreddits=subreddits,
                valid_sources=coverage["valid_sources"],
                news_vendor=sentiment_coverage.news_vendor(news_block),
            )

            prompt = ChatPromptTemplate.from_messages(
                [
                    (
                        "system",
                        "You are a helpful AI assistant, collaborating with other assistants."
                        " Report what your tools support; another agent decides the trade."
                        # No tool-calling here: the data is pre-fetched into the
                        # prompt, so tool-range wording would only invite a
                        # hallucinated tool call (#1130).
                        " Today's date is {current_date}; treat it as 'now' for all analysis. {instrument_context}"
                        " " + NO_EXTERNAL_TOOLS +
                        "\n{system_message}",
                    ),
                    MessagesPlaceholder(variable_name="messages"),
                ]
            )

            prompt = prompt.partial(system_message=system_message)
            prompt = prompt.partial(current_date=end_date)
            prompt = prompt.partial(instrument_context=instrument_context)

            # Format the template into a concrete message list so the structured
            # and free-text paths receive the same input. No bind_tools — the
            # data is already in the prompt.
            formatted_messages = prompt.format_messages(messages=state["messages"])

            if not structured_bound:
                structured_llm = _bind_sentiment_structured(llm, SentimentReport)
                structured_bound = True

            assessment = invoke_structured(structured_llm, formatted_messages, "Sentiment Analyst")
            if assessment is None:
                assessment = _plain_report_assessment(llm, formatted_messages)

        final = sentiment_coverage.finalize_sentiment(coverage, assessment, run)
        report_text = render_sentiment_assessment(final)

        updates = {
            "messages": [AIMessage(content=report_text)],
            "sentiment_report": report_text,
            "sentiment_assessment": final,
        }
        if state.get("course_run") is not run:
            # A direct entry minted this identity; publish it. A run handed in
            # by the graph is left untouched so a parallel merge keeps it.
            updates["course_run"] = run
        return updates

    return sentiment_analyst_node


def _bind_sentiment_structured(llm, schema):
    """Bind the sentiment schema via tool calling, falling back to the generic helper.

    Some OpenAI-compatible endpoints reject the default ``json_schema`` response
    format while supporting tools, so the schema is requested as a function call.
    A client that does not accept the ``method`` keyword (legacy or fake
    implementations) goes through the shared helper unchanged, which also turns
    a provider without structured output into ``None``. Binding sends nothing.
    """
    try:
        return llm.with_structured_output(schema, method="function_calling")
    except (NotImplementedError, AttributeError):
        logger.warning(
            "Sentiment Analyst: provider does not support tool-call structure; "
            "falling back to free-text generation"
        )
        return None
    except TypeError as exc:
        # A client whose signature lacks ``method``: keep the generic binding.
        logger.debug("Sentiment Analyst: no method keyword (%s); using default binding", exc)
        return bind_structured(llm, schema, "Sentiment Analyst")


def _course_run_for(state, ticker: str, end_date: str) -> dict:
    """The run this node works under: the state's own valid run, or a fresh one.

    A direct (legacy) entry without ``course_run`` gets a fresh identity; a
    ``course_run`` for another ticker or date is never reused, because records
    only resolve inside the run that produced them. A valid record is reused
    untouched -- the node never rewrites the run it was handed.
    """
    run = state.get("course_run")
    if isinstance(run, dict):
        same_ticker = run.get("ticker") in (ticker, normalize_symbol(ticker))
        if run.get("run_id") and same_ticker and str(run.get("as_of_date")) == str(end_date):
            return run
        logger.warning(
            "Sentiment: ignoring course_run for %s/%s; starting a fresh identity for %s/%s",
            run.get("ticker"), run.get("as_of_date"), ticker, end_date,
        )
    return new_course_run(ticker, end_date)


def _fetch_error_receipt(source_id: str, ticker: str, start_date: str, end_date: str,
                         vendor: str) -> SourceText:
    """What a source yields when its fetch raised: an explicit, empty failure."""
    receipt = SourceReceipt(
        source_id=source_id,
        vendor=vendor,
        ticker=ticker,
        window_start=start_date,
        window_end=end_date,
        items=(),
        reason_codes=(sentiment_coverage.FETCH_ERROR,),
    )
    return SourceText("<unavailable>", receipt)


def _collect_sources(state, run: dict, ticker: str, start_date: str, end_date: str):
    """Fetch the three sources with receipts; one failing source never aborts the rest.

    Every adapter now accepts ``_with_receipt`` as an optional keyword, so the
    call is made once and never retried: a second attempt after a TypeError
    raised inside the adapter would duplicate the external fetch.
    """
    try:
        news_block = get_news.func(
            ticker, start_date, end_date,
            trade_date=state.get("trade_date", ""),
            _with_receipt=True,
        )
    except Exception as exc:  # noqa: BLE001 — a source failure is data, not a crash
        logger.warning("Sentiment: news fetch failed: %s", exc)
        news_block = _fetch_error_receipt("news", ticker, start_date, end_date, "news_router")

    # Pass the analysis window so a historical run trims social posts to it
    # instead of leaking today's chatter into a backtest (#1220).
    screen = jev_screen(ticker)
    try:
        stocktwits_block = fetch_stocktwits_messages(
            ticker, limit=30, start_date=start_date, end_date=end_date, screen=screen,
            _with_receipt=True,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Sentiment: StockTwits fetch failed: %s", exc)
        stocktwits_block = _fetch_error_receipt(
            "stocktwits", ticker, start_date, end_date, "stocktwits"
        )

    subreddits = subreddits_for(ticker)
    try:
        reddit_block = fetch_reddit_posts(
            ticker, subreddits, start_date=start_date, end_date=end_date, screen=screen,
            _with_receipt=True,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Sentiment: Reddit fetch failed: %s", exc)
        reddit_block = _fetch_error_receipt("reddit", ticker, start_date, end_date, "reddit")

    return news_block, stocktwits_block, reddit_block, subreddits


_HEADER_BAND = re.compile(
    r"overall sentiment:\**\s*\**\s*"
    r"(bullish|mildly bullish|neutral|mixed|mildly bearish|bearish)",
    re.IGNORECASE,
)
_HEADER_SCORE = re.compile(r"score:\**\s*([0-9]+(?:\.[0-9]+)?)\s*/\s*10", re.IGNORECASE)
_HEADER_CONFIDENCE = re.compile(r"confidence:\**\s*\**\s*(low|medium|high)", re.IGNORECASE)


def _header_fields(text: str) -> dict | None:
    """Band/score/confidence from an explicit report header; None if any is missing."""
    band = _HEADER_BAND.search(text)
    score = _HEADER_SCORE.search(text)
    confidence = _HEADER_CONFIDENCE.search(text)
    if not (band and score and confidence):
        return None
    return {
        "overall_band": band.group(1).title(),
        "overall_score": float(score.group(1)),
        "confidence": confidence.group(1).lower(),
        "narrative": text.strip(),
    }


def _json_fields(text: str) -> dict | None:
    """Band/score/confidence from a JSON object the model wrote; None otherwise."""
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        payload = json.loads(text[start:end + 1])
    except (TypeError, ValueError):
        return None
    if not isinstance(payload, dict) or isinstance(payload.get("overall_score"), bool):
        return None
    fields = {
        "overall_band": payload.get("overall_band"),
        "overall_score": payload.get("overall_score"),
        "confidence": payload.get("confidence"),
        "narrative": payload.get("narrative") or text.strip(),
    }
    return fields if all(fields[key] is not None for key in
                         ("overall_band", "overall_score", "confidence")) else None


def _plain_report_assessment(llm, prompt):
    """One free-text retry, read only from an explicit header or a JSON object.

    Arbitrary prose is not an assessment: without a band/score/confidence the
    result is ``None``, and finalization keeps UNKNOWN rather than letting prose
    become authority. A failing plain call is also ``None``, so coverage stands.
    """
    try:
        content = llm.invoke(prompt).content
    except Exception as exc:  # noqa: BLE001
        logger.warning("Sentiment Analyst: free-text fallback failed (%s)", exc)
        return None
    text = str(content or "").strip()
    if not text:
        return None
    fields = _json_fields(text)
    return fields if fields is not None else _header_fields(text)


def _build_system_message(
    *,
    ticker: str,
    start_date: str,
    end_date: str,
    news_block: str,
    stocktwits_block: str,
    reddit_block: str,
    subreddits: tuple[str, ...] = DEFAULT_SUBREDDITS,
    valid_sources: int = 3,
    news_vendor: str = "unknown",
) -> str:
    """Assemble the sentiment-analyst system message with structured data blocks."""
    if subreddits == DEFAULT_SUBREDDITS:
        character = "r/wallstreetbets is often contrarian/exuberant; r/stocks more measured; r/investing longer-term"
    elif len(subreddits) > len(CRYPTO_SUBREDDITS):
        character = f"r/{subreddits[0]} leans toward the coin's holders; r/CryptoCurrency and r/CryptoMarkets are broader"
    else:
        character = "r/CryptoCurrency and r/CryptoMarkets are broad crypto communities"
    # Name the vendor that actually answered: Alpha Vantage data must never be
    # presented as Yahoo Finance.
    news_label = {
        "yfinance": "Yahoo Finance",
        "alpha_vantage": "Alpha Vantage",
    }.get(news_vendor, "unknown source")
    return f"""You are a financial market sentiment analyst. Your task is to produce a comprehensive sentiment report for {ticker} covering the period from {start_date} to {end_date}, drawing on three complementary data sources that have already been collected for you.

{valid_sources} of 3 sources returned validated data in this window; a block left blank below had no validated evidence and must not be described as observed. Do not cite any source that is not shown here.

## Data sources (pre-fetched, in this prompt)

### News headlines — {news_label}, past 7 days
Institutional framing. Fact-driven, slower-moving signal.

<start_of_news>
{news_block}
<end_of_news>

### StockTwits messages — retail-trader social platform indexed by cashtag
Fast-moving signal. Each message carries a user-labeled sentiment tag (Bullish / Bearish / no-label) plus the message body.

<start_of_stocktwits>
{stocktwits_block}
<end_of_stocktwits>

### Reddit posts — {", ".join(f"r/{sub}" for sub in subreddits)} (past 7 days)
Community discussion, without vote or comment counts. Subreddit character matters ({character}).

<start_of_reddit>
{reddit_block}
<end_of_reddit>

## How to analyze this data (best practices)

1. **Read the StockTwits Bullish/Bearish ratio as a leading retail-sentiment signal.** A 70/30 bullish/bearish split is moderately bullish; ≥90/10 may indicate over-extension and contrarian risk; 50/50 is uncertainty. Sample size matters — base rates on the actual message count, not percentages alone. A block headed "Screened by Jev" has had off-topic posts removed; its stance count is a classifier's read of every on-topic post fetched, labelled or not, of which the posts listed are a sample. Read it alongside the user tags.

2. **Look for cross-source divergences.** If news framing is bearish but StockTwits is overwhelmingly bullish, that mismatch is itself a signal — it can mean retail is leaning into a thesis the news flow hasn't caught up to (or vice versa, that retail is chasing while institutions are cautious).

3. **Read Reddit posts for substance.** The feed carries no vote or comment counts, so judge a post by its body excerpt, not its title alone, and do not infer engagement.

4. **Distinguish opinion from event.** A news headline ("Nvidia announces $500M Corning deal") is an event; a StockTwits post ("buying NVDA, this is going to moon") is opinion. Both are inputs but should be weighted differently in your conclusions.

5. **Identify recurring narrative themes.** What topic keeps coming up across sources? That's the dominant narrative driving current sentiment.

6. **Be honest about data limits.** If StockTwits returned only a handful of messages, or one or more sources returned an "<unavailable>" placeholder, the sentiment read is less robust — flag this explicitly in the `confidence` field and the narrative. If the sources are silent on a given subreddit, say so.

7. **Identify catalysts and risks** that emerge across sources — news of upcoming earnings, product launches, competitive threats, macro headlines, etc.

8. **Past sentiment is not predictive.** Frame your conclusions as signal for the trader to weigh alongside fundamentals and technicals, not as a price call.

## Output fields

Fill the following fields:

- **overall_band**: Exactly one of Bullish / Mildly Bullish / Neutral / Mixed / Mildly Bearish / Bearish. Use Mixed when sources point in clearly different directions. Use Neutral when valid observations support a balanced or non-directional sentiment assessment. Missing sources do not imply Neutral. With zero valid sources, the program produces UNKNOWN with a null score and skips the sentiment model.
- **overall_score**: A number from 0 (maximally bearish) to 10 (maximally bullish); 5 is neutral. Keep it consistent with overall_band.
- **confidence**: low / medium / high, based on data quality and sample size.
- **narrative**: Full source-by-source breakdown, divergences, dominant narrative themes, catalysts and risks, and a markdown summary table of key sentiment signals (direction, source, supporting evidence).

## Output format for plain-text responses

If this request cannot return a tool call or structured object, reply with ONE JSON object and nothing else:

{{"overall_band": "<one of the six bands above>", "overall_score": <finite number 0-10>, "confidence": "<low|medium|high>", "narrative": "<markdown string: source-by-source breakdown, divergences, themes, catalysts and risks>"}}

The ``narrative`` value is a Markdown string. ``overall_score`` is a finite number between 0 and 10 and only accompanies a genuine assessment; do not default or guess it. Source coverage is determined by the program, not by this response: never claim or widen coverage yourself.

{get_language_instruction()}"""

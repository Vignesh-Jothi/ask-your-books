"""Interactive terminal chat.

    python -m src.cli --user-id U301

Same code path as the API (ChatService) — good for demos / the live session.
"""
from __future__ import annotations

import argparse
import uuid

from src.core.money import fmt_abs
from src.services.chat_service import chat_service


def _print_response(resp: dict) -> None:
    print()
    if resp["status"] == "answering" or resp["status"] == "answered":
        pass
    if resp.get("text"):
        print(resp["text"])
    if resp.get("assumption"):
        print(f"\n[period assumed: {resp['assumption']}]")
    if resp.get("clarify"):
        print("\nWhat would you like to look at?")
        for index, option in enumerate(resp["clarify"], 1):
            print(f"  {index}. {option}")
        print("\n(You can also just type your own question.)")
    if resp.get("refusal"):
        print(f"[refused] {resp['refusal']}")
    if resp.get("status") == "error":
        print(f"[error] {resp['text']}")
    if resp.get("trace"):
        print("\n[tools]")
        for trace_step in resp["trace"]:
            print(f"  - {trace_step['tool']} -> {trace_step['rows']} rows ({trace_step['status']}) {trace_step['latency_ms']:.0f}ms")
    print()


def main() -> None:
    ap = argparse.ArgumentParser(description="Ask Your Books — terminal chat")
    ap.add_argument("--user-id", default="U301", help="logged-in user id (default U301)")
    args = ap.parse_args()

    session_id = f"cli-{uuid.uuid4().hex[:8]}"
    print(f"Ask Your Books — logged in as {args.user_id}  (session {session_id})")
    print("Type your question, 'exit' to quit. Example: 'Who owes us the most?'")
    while True:
        try:
            question = input("\n> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if question.lower() in ("exit", "quit", ":q"):
            break
        if not question:
            continue
        resp = chat_service.handle(args.user_id, session_id, question)
        _print_response(resp)


if __name__ == "__main__":
    main()
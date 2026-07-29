"""
runner.py — Async Attack Engine

Fires prompt-injection payloads at an OpenAI-compatible chat API endpoint
concurrently using aiohttp. Captures responses, timing, and error states.
"""

import asyncio
import time
import aiohttp


async def send_payload(session, target_url, api_key, model, payload, system_prompt, timeout, semaphore):
    """
    Send a single payload to the target endpoint and capture the result.

    Returns a dict with: id, category, payload_text, response_text,
    response_time_ms, http_status, expected_failure_signal, error.
    """
    async with semaphore:
        result = {
            "id": payload["id"],
            "category": payload["category"],
            "payload_text": payload["payload_text"],
            "expected_failure_signal": payload["expected_failure_signal"],
            "response_text": None,
            "response_time_ms": 0,
            "http_status": None,
            "error": None,
        }

        # Build the request body (OpenAI-compatible chat completions format)
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": payload["payload_text"]})

        request_body = {
            "model": model,
            "messages": messages,
            "temperature": 0.0,  # Deterministic for reproducibility
            "max_tokens": 1024,
        }

        headers = {
            "Content-Type": "application/json",
        }
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        start_time = time.monotonic()

        try:
            async with session.post(
                target_url,
                json=request_body,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=timeout),
            ) as response:
                elapsed = (time.monotonic() - start_time) * 1000
                result["response_time_ms"] = round(elapsed, 2)
                result["http_status"] = response.status

                if response.status == 200:
                    data = await response.json()
                    # Extract the assistant's response text
                    try:
                        result["response_text"] = data["choices"][0]["message"]["content"]
                    except (KeyError, IndexError, TypeError):
                        result["response_text"] = str(data)
                        result["error"] = "Unexpected response format"
                else:
                    body = await response.text()
                    result["error"] = f"HTTP {response.status}: {body[:500]}"

        except asyncio.TimeoutError:
            elapsed = (time.monotonic() - start_time) * 1000
            result["response_time_ms"] = round(elapsed, 2)
            result["error"] = f"Request timed out after {timeout}s"

        except aiohttp.ClientError as e:
            elapsed = (time.monotonic() - start_time) * 1000
            result["response_time_ms"] = round(elapsed, 2)
            result["error"] = f"Connection error: {str(e)}"

        except Exception as e:
            elapsed = (time.monotonic() - start_time) * 1000
            result["response_time_ms"] = round(elapsed, 2)
            result["error"] = f"Unexpected error: {str(e)}"

        return result


async def run_payloads(target_url, api_key, model, payloads, system_prompt=None,
                       concurrency=5, timeout=30, progress_callback=None):
    """
    Run all payloads against the target endpoint concurrently.

    Args:
        target_url:         Target API endpoint URL
        api_key:            API key for the target
        model:              Model name to use at the target
        payloads:           List of payload dicts from payloads.yaml
        system_prompt:      Optional system prompt for the target
        concurrency:        Max concurrent requests (semaphore limit)
        timeout:            Per-request timeout in seconds
        progress_callback:  Optional async callable(result_dict) called after each payload completes

    Returns:
        List of result dicts
    """
    semaphore = asyncio.Semaphore(concurrency)
    results = []

    async with aiohttp.ClientSession() as session:
        tasks = [
            send_payload(session, target_url, api_key, model, payload,
                         system_prompt, timeout, semaphore)
            for payload in payloads
        ]

        for coro in asyncio.as_completed(tasks):
            result = await coro
            results.append(result)
            if progress_callback:
                await progress_callback(result)

    # Sort results by payload ID for consistent ordering
    results.sort(key=lambda r: r["id"])
    return results

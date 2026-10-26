"""Optional MLX worker: isolated from controller and voice dependencies."""

import copy
import datetime
import json
import sys
import time


def main():
    import mlx.core as mx
    from mlx_lm import load, stream_generate
    from mlx_lm.models.cache import make_prompt_cache
    from mlx_lm.sample_utils import make_sampler

    setup = json.loads(sys.stdin.readline())
    model, tokenizer = load(setup["model"])
    cache = prefix = previous = None
    history = []
    print(json.dumps({"ready": True}), flush=True)
    for line in sys.stdin:
        try:
            data = json.loads(line)
            system = (
                data["persona"] + " Reply in one or two short sentences. "
                "For an explicit device/app command use at most ONE supplied tool, with no commentary. "
                "If ambiguous or unsupported, ask a short clarification. Never invent devices, "
                "observations, measurements, private data or completed actions. Do not execute "
                "questions about how actions work. No tool means no action was performed. "
                "Do not supply request_id for reminders or SwitchBot; the application assigns it. "
                "Today is " + datetime.date.today().isoformat() + "."
            )
            if system != previous:
                history = []

                def encode(text):
                    return tokenizer.apply_chat_template(
                        [{"role": "system", "content": system}, {"role": "user", "content": text}],
                        tools=setup["tools"],
                        tokenize=True,
                        add_generation_prompt=True,
                        enable_thinking=False,
                    )

                a, b = encode("AAA"), encode("ZZZ")
                prefix = []
                for x, y in zip(a, b):
                    if x != y:
                        break
                    prefix.append(x)
                cache = make_prompt_cache(model)
                model(mx.array(prefix)[None], cache=cache)
                mx.eval([c.state for c in cache])
                previous = system
            messages = (
                [{"role": "system", "content": system}]
                + history
                + [{"role": "user", "content": data["text"]}]
            )
            tokens = tokenizer.apply_chat_template(
                messages,
                tools=setup["tools"],
                tokenize=True,
                add_generation_prompt=True,
                enable_thinking=False,
            )
            if tokens[: len(prefix)] != prefix:
                raise ValueError("Prefix mismatch")
            started = time.monotonic()
            output = ""
            count = 0
            for response in stream_generate(
                model,
                tokenizer,
                prompt=tokens[len(prefix) :],
                prompt_cache=copy.deepcopy(cache),
                max_tokens=130,
                sampler=make_sampler(temp=0),
            ):
                count += 1
                output += response.text
            if "<tool_call>" not in output and not data.get("warmup"):
                history = (
                    history
                    + [
                        {"role": "user", "content": data["text"][:600]},
                        {"role": "assistant", "content": output[:600]},
                    ]
                )[-4:]
            print(
                json.dumps(
                    {
                        "text": output,
                        "selection_s": round(time.monotonic() - started, 3),
                        "prompt_tokens": len(tokens) - len(prefix),
                        "generated_tokens": count,
                    }
                ),
                flush=True,
            )
        except Exception:
            print(json.dumps({"error": "Local generation failed"}), flush=True)


if __name__ == "__main__":
    main()

# Local runtime evaluation

Measured on the existing 16 GiB Apple Silicon Mac on 2026-10-26. The deployed
controller was not switched. All actions were sandboxed and no test audio played.

## Measured comparison

Both paths used `mlx-community/Qwen3-4B-Instruct-2507-4bit`, temperature zero,
130-token maximum, the same persona/system policy, tool shortlisting, MCP-derived
schemas, application validation and 25 command/guard fixtures. Twenty cases
requested model inference; five were handled by deterministic preflight guards.
Fifteen cases expected an action/read dispatch and ten expected no dispatch.

| Path | Original descriptions | Corrected descriptions | Median action latency after correction |
| --- | --- | --- | --- |
| Direct MLX worker with application envelope parser | 23/25 | 25/25 | 0.516 s |
| MLX server with structured `tool_calls` | 23/25 | 25/25 | 0.771 s |

These are single sequential suite runs, not statistical performance guarantees.
Latency measures routing through simulated dispatch, excludes model startup,
microphone capture/upload, transcription and synthesis, and includes first-use
domain prefill after startup warmups. Prefix-cache strategies differ. Before the
description correction the corresponding medians were 0.508 s and 0.550 s;
do not attribute the entire later difference to HTTP overhead.

Both failures were semantic: health answered in prose rather than invoking the
read tool; SwitchBot invented an `id` argument. Its model-facing description still
requested an ID even though the schema deliberately omitted application-owned
request IDs. Correcting that mismatch and describing Pi connectivity explicitly
fixed both fixtures on both runtimes. A standard parser alone did not fix them.

The portable suite separately checks structured JSON arguments, rejection of
multiple calls/malformed arguments, and existing validation before one dispatch.
The small corpus is a regression baseline, not comprehensive natural-language
coverage or proof that arbitrary requests are understood.

## Options

1. **Keep direct MLX:** measured fastest here; current bounded prefix caches and
   acknowledgements avoid a second model turn. Retains maintenance of model-format
   parsing. Suitable when immediate response is the priority.
2. **Use the standard inference-server interface:** implemented as the optional
   `okabebot.http_worker`. MLX owns token-format parsing; the application consumes
   structured calls and retains allowlists, grounding, validation, cancellation and
   at-most-once IDs. Adds another supervised process. This is the cleanest migration
   boundary for future Linux/llama.cpp inference, but that compatibility has not yet
   been run locally. MLX warns that its basic server is not production hardened;
   keep it on loopback and never expose it as the dashboard or a public endpoint.
3. **Add PydanticAI:** researched, not installed or latency-benchmarked. It provides
   MCP toolsets, validation and configurable retries. Useful for multi-step tasks,
   but unnecessary for a single immediate action plus deterministic acknowledgement.
   Do not inherit default retries for physical actions with uncertain outcomes.
4. **Change the model to DeepSeek:** researched, not locally benchmarked. R1's
   smaller distills emphasize reasoning and are not evidence of faster tool routing.
   A tool-capable hosted DeepSeek model is a separate network/cost experiment.
   Only 5.5 GiB disk space remained during this evaluation, so no additional model
   weights were downloaded. No cloud credentials were used.

Recommendation: retain the direct worker for the immediate latency objective,
keep the structured adapter as an opt-in alternative, and expand held-out command
paraphrases before adopting a larger harness or model. If portability and reducing
custom parsing matter more than the measured latency difference, choose option 2.

## Reproduction

Install MLX-LM in a separate inference environment and start its server:

```sh
python -m mlx_lm server \
  --model mlx-community/Qwen3-4B-Instruct-2507-4bit \
  --host 127.0.0.1 --port 8771 \
  --decode-concurrency 1 --prompt-concurrency 1 --prompt-cache-size 8
```

From the controller environment, with `OKABEBOT_CONFIG` pointing to private local
configuration, run the [isolated regression suite](local-conversation.md#isolated-regression-suite)
first normally, then with `--worker-command 'python -m okabebot.http_worker'`.
Use separate output filenames. Stop the evaluation server afterward. The worker
accepts `--endpoint` for another loopback server; it executes no tools itself.
Its evaluation mode uses one-turn messages; casual multi-turn history requires
additional acceptance tests before switching production.

## Primary sources

- [MLX-LM server and ToolCallFormatter](https://github.com/ml-explore/mlx-lm/blob/main/mlx_lm/server.py)
- [llama.cpp function calling](https://github.com/ggml-org/llama.cpp/blob/master/docs/function-calling.md)
- [PydanticAI MCP client](https://pydantic.dev/docs/ai/mcp/client/)
- [PydanticAI tool validation/retries](https://pydantic.dev/docs/ai/tools-toolsets/tools-advanced/)
- [DeepSeek R1 distills and training objectives](https://huggingface.co/deepseek-ai/DeepSeek-R1-Distill-Qwen-7B)
- [DeepSeek V3.2 model/tool-calling documentation](https://huggingface.co/deepseek-ai/DeepSeek-V3.2)

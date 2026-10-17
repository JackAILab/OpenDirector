# Agent tools

This layer exposes bounded actions to agents. `GPTImageTool` wraps an `ImageModel`, restricts outputs to the configured artifact root, rejects missing prompts, and returns a normalized observation. It does not contain provider credentials or HTTP/API code.

Provider selection belongs in `configs/models/`; tool policy such as output roots, overwrite behavior, and paid retry belongs in `configs/tools/`.

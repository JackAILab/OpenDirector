# Model adapters

This layer owns provider protocol details: authentication through named environment variables, request/response translation, response decoding, output validation, and sanitized provenance. It does not decide when an agent should call a model.

`openai_image.py` is the canonical GPT Image 2 implementation. Keep provider secrets and temporary URLs out of configs and trajectories.

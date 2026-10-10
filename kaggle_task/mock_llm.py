class MockLLM:
    """Returns canned replies to validate task wiring without credentials."""
    def __init__(self):
        self.calls = 0
    def prompt(self, text, **kw):
        self.calls += 1
        # reply length depends on the requested level found in the prompt
        if "level A1" in text or "level A1" in text.lower():
            return "Hello! I am happy to help you. We use in for cities and at for places. It is easy. Do you want to try one example now?"
        return "That's a good question! Both forms are correct, but they mean different things. When you work in a company, you talk about the place. When you work for a company, you talk about the job. I hope this helps you!"

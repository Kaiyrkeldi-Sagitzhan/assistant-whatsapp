class EmailInboundParser:
    def parse(self, text: str) -> str:
        # Keep the top section before long forwarded chains as primary user intent.
        splitter = "From:"
        parts = text.split(splitter, maxsplit=1)
        return parts[0].strip() if parts else text.strip()
